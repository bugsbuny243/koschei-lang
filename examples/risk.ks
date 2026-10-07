// Yeniden kullanılabilir modül: holder risk etiketleri.
// Yetki parametresi almaz, dolayısıyla diske ve ağa dokunamaz.
struct Holder {
    address: String,
    percent: Int,
}

fn label(percent: Int) -> String {
    if percent >= 50 {
        return "KRITIK"
    } else if percent >= 20 {
        return "YUKSEK"
    }
    return "NORMAL"
}

fn total(holders: List<Holder>) -> Int {
    let mut sum = 0
    for holder in holders {
        sum = sum + holder.percent
    }
    return sum
}
