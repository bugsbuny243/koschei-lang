struct Product {
    id: String,
    stock: Int,
}

fn available(product: Product) -> Bool {
    return product.stock > 0
}

fn stock_ok(stock: Int) -> Bool {
    return stock > 0
}

fn main() {
    let sample = Product { id: "SKU-1", stock: 12 }
    println("domain-ready:{available(sample)}")
}
