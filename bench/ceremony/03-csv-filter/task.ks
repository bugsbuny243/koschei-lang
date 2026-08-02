fn main() {
    let csv = "name,active\nAda,true\nLin,false\nGrace,true"
    for row in csv.split("\n") {
        if row == "name,active" { continue }
        let fields = row.split(",")
        if (fields.get(1) or "false") != "true" { continue }
        println(fields.get(0) or "")
    }
}
