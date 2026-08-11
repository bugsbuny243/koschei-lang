struct CatalogItem {
    sku: String,
    price_ticks: Int,
}

fn display_price(item: CatalogItem) -> String {
    return "{item.sku}:{item.price_ticks}"
}

fn main() {
    let item = CatalogItem { sku: "SKU-1", price_ticks: 12500 }
    println(display_price(item))
}
