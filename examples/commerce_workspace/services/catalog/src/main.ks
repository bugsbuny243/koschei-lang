import domain

struct CatalogItem {
    sku: String,
    price_ticks: Int,
}

fn sellable(stock: Int) -> Bool {
    return domain.stock_ok(stock)
}

fn display_price(item: CatalogItem) -> String {
    return "{item.sku}:{item.price_ticks}"
}

fn main() {
    let item = CatalogItem { sku: "SKU-1", price_ticks: 12500 }
    println("catalog-ready:{sellable(12)}:{display_price(item)}")
}
