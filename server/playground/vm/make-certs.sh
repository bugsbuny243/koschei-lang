#!/bin/sh
# Create (or keep) the worker's private CA and its server certificate.
#   make-certs.sh DIR SAN CN
# SAN is an openssl subjectAltName value, e.g. "DNS:worker.example.com,IP:10.0.0.5".
# Writes DIR/ca-cert.pem, ca-key.pem, tls-cert.pem, tls-key.pem, tls-names.
#
# The frontend verifies the chain with strict X.509 checks (Python 3.13's
# default, enforced on every version by koschei/playground_remote.py), so the
# CA carries keyUsage and key identifiers. A CA without keyUsage, from older
# installs, is replaced. The chain is verified before the script succeeds.
set -eu
DIR=${1:?directory}
SAN=${2:?subjectAltName}
CN=${3:?common name}
umask 077
if [ -s "$DIR/ca-cert.pem" ] && ! openssl x509 -in "$DIR/ca-cert.pem" -noout -ext keyUsage 2>/dev/null | grep -q "Certificate Sign"; then
  rm -f "$DIR/ca-key.pem" "$DIR/ca-cert.pem" "$DIR/tls-key.pem" "$DIR/tls-cert.pem" "$DIR/tls-names"
fi
if [ ! -s "$DIR/ca-key.pem" ]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 825 \
    -subj "/CN=Koschei worker CA" -keyout "$DIR/ca-key.pem" -out "$DIR/ca-cert.pem" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" 2>/dev/null
  rm -f "$DIR/tls-key.pem"
fi
if [ ! -s "$DIR/tls-key.pem" ] || [ "$(cat "$DIR/tls-names" 2>/dev/null)" != "$SAN" ]; then
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=$CN" \
    -keyout "$DIR/tls-key.pem" -out "$DIR/tls.csr" 2>/dev/null
  printf '%s\n' "subjectAltName=$SAN" "extendedKeyUsage=serverAuth" \
    "keyUsage=critical,digitalSignature" "basicConstraints=critical,CA:FALSE" \
    "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid:always" > "$DIR/tls.ext"
  openssl x509 -req -in "$DIR/tls.csr" -CA "$DIR/ca-cert.pem" -CAkey "$DIR/ca-key.pem" \
    -CAcreateserial -days 397 -extfile "$DIR/tls.ext" -out "$DIR/tls-cert.pem" 2>/dev/null
  rm -f "$DIR/tls.csr" "$DIR/tls.ext"
  printf '%s\n' "$SAN" > "$DIR/tls-names"
fi
openssl verify -x509_strict -purpose sslserver -CAfile "$DIR/ca-cert.pem" "$DIR/tls-cert.pem" >/dev/null \
  || { echo "worker certificate fails strict verification" >&2; exit 1; }
