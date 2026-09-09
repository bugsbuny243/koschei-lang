(() => {
  'use strict';

  const sdkStatus = document.getElementById('sdk-status');
  const signInButton = document.getElementById('signin');
  const result = document.getElementById('result');
  const username = document.getElementById('username');
  const uid = document.getElementById('uid');
  const errorBox = document.getElementById('error');

  function showError(error) {
    result.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent = error instanceof Error ? error.message : String(error);
  }

  function onIncompletePaymentFound(payment) {
    // V1 intentionally does not mutate/complete payments from the browser.
    // The production backend will resolve incomplete payments using Pi Platform API.
    console.warn('Pi sandbox found an incomplete payment:', payment?.identifier || 'unknown');
  }

  if (!window.Pi || typeof window.Pi.init !== 'function') {
    sdkStatus.textContent = 'unavailable';
    showError('Pi SDK did not load. Open this page through the Pi sandbox flow and retry.');
    return;
  }

  try {
    window.Pi.init({ version: '2.0', sandbox: true });
    sdkStatus.textContent = 'ready';
    signInButton.disabled = false;
  } catch (error) {
    sdkStatus.textContent = 'error';
    showError(error);
    return;
  }

  signInButton.addEventListener('click', async () => {
    signInButton.disabled = true;
    signInButton.textContent = 'Connecting…';
    errorBox.hidden = true;

    try {
      const auth = await window.Pi.authenticate(['username'], onIncompletePaymentFound);
      username.textContent = auth?.user?.username || 'unknown';
      uid.textContent = auth?.user?.uid || 'unknown';
      result.hidden = false;
      signInButton.textContent = 'Pi connected';
    } catch (error) {
      signInButton.disabled = false;
      signInButton.textContent = 'Continue with Pi';
      showError(error);
    }
  });
})();
