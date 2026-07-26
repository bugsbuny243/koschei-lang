enum Delivery {
    Pending,
    Sent(String),
    Failed(Error),
}

fn find_customer(active: Bool) -> Option<String> {
    if active {
        return Some("Onur")
    }
    return None()
}

fn deliver(active: Bool) -> Result<Delivery, Error> {
    let customer = find_customer(active) or return Err(Error("Müşteri bulunamadı"))
    return Ok(Sent("Gönderildi: {customer}"))
}

fn describe(result: Result<Delivery, Error>) -> String {
    return match result {
        Ok(delivery) => match delivery {
            Pending => "bekliyor",
            Sent(message) => message,
            Failed(error) => "teslimat hatası",
        },
        Err(error) => "işlem başarısız",
    }
}

fn main() {
    println(describe(deliver(true)))
    println(describe(deliver(false)))
}
