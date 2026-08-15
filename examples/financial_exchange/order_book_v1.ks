// Koschei Financial Infrastructure P2: deterministic in-memory venue core.
//
// This reference is deliberately pure: it owns no disk, network, process, env,
// clock, custody, or chain capability. Price and quantity are integer ticks/lots.
// External decimal conversion belongs outside this matching boundary.

enum Side {
    Buy,
    Sell,
}

struct VenuePolicy {
    tick_size_ticks: Int,
    lot_size_lots: Int,
    max_order_lots: Int,
    reject_self_trade: Bool,
}

struct BookOrder {
    id: String,
    owner_id: String,
    side: Side,
    price_ticks: Int,
    quantity_lots: Int,
    sequence: Int,
}

struct BookTrade {
    maker_id: String,
    taker_id: String,
    price_ticks: Int,
    quantity_lots: Int,
    maker_sequence: Int,
    taker_sequence: Int,
}

struct AcceptedEvent {
    order_id: String,
    sequence: Int,
}

struct CanceledEvent {
    order_id: String,
    sequence: Int,
}

struct ReplacedEvent {
    order_id: String,
    previous_sequence: Int,
    sequence: Int,
    price_ticks: Int,
    quantity_lots: Int,
}

enum BookEvent {
    OrderAccepted(AcceptedEvent),
    TradeExecuted(BookTrade),
    OrderCanceled(CanceledEvent),
    OrderReplaced(ReplacedEvent),
}

struct OrderBook {
    bids: List<BookOrder>,
    asks: List<BookOrder>,
    seen_ids: List<String>,
    last_sequence: Int,
    events: List<BookEvent>,
}

fn empty_book() -> OrderBook {
    let bids: List<BookOrder> = []
    let asks: List<BookOrder> = []
    let seen_ids: List<String> = []
    let events: List<BookEvent> = []
    return OrderBook {
        bids: bids,
        asks: asks,
        seen_ids: seen_ids,
        last_sequence: -1,
        events: events,
    }
}

fn min_int(left: Int, right: Int) -> Int {
    if left <= right {
        return left
    }
    return right
}

fn valid_policy(policy: VenuePolicy) -> Bool {
    return policy.tick_size_ticks > 0 && policy.lot_size_lots > 0 && policy.max_order_lots > 0
}

fn valid_new_order(order: BookOrder, policy: VenuePolicy) -> Bool {
    if !valid_policy(policy) {
        return false
    }
    if order.price_ticks <= 0 || order.quantity_lots <= 0 || order.sequence < 0 {
        return false
    }
    if order.quantity_lots > policy.max_order_lots {
        return false
    }
    if order.price_ticks % policy.tick_size_ticks != 0 {
        return false
    }
    return order.quantity_lots % policy.lot_size_lots == 0
}

fn sequence_is_new(book: OrderBook, sequence: Int) -> Bool {
    return sequence > book.last_sequence
}

fn active_order_exists(book: OrderBook, id: String) -> Bool {
    for order in book.bids {
        if order.id == id {
            return true
        }
    }
    for order in book.asks {
        if order.id == id {
            return true
        }
    }
    return false
}

fn find_active_order(book: OrderBook, id: String) -> Option<BookOrder> {
    for order in book.bids {
        if order.id == id {
            return Some(order)
        }
    }
    for order in book.asks {
        if order.id == id {
            return Some(order)
        }
    }
    return None()
}

fn crosses(incoming: BookOrder, resting: BookOrder) -> Bool {
    if incoming.side == Buy() && resting.side == Sell() {
        return incoming.price_ticks >= resting.price_ticks
    }
    if incoming.side == Sell() && resting.side == Buy() {
        return resting.price_ticks >= incoming.price_ticks
    }
    return false
}

fn self_trade_preflight(book: OrderBook, incoming: BookOrder, policy: VenuePolicy) -> Bool {
    if !policy.reject_self_trade {
        return true
    }
    if incoming.side == Buy() {
        for resting in book.asks {
            if crosses(incoming, resting) && incoming.owner_id == resting.owner_id {
                return false
            }
        }
        return true
    }
    for resting in book.bids {
        if crosses(incoming, resting) && incoming.owner_id == resting.owner_id {
            return false
        }
    }
    return true
}

fn bid_before(left: BookOrder, right: BookOrder) -> Bool {
    if left.price_ticks > right.price_ticks {
        return true
    }
    if left.price_ticks < right.price_ticks {
        return false
    }
    return left.sequence < right.sequence
}

fn ask_before(left: BookOrder, right: BookOrder) -> Bool {
    if left.price_ticks < right.price_ticks {
        return true
    }
    if left.price_ticks > right.price_ticks {
        return false
    }
    return left.sequence < right.sequence
}

fn insert_bid(bids: List<BookOrder>, order: BookOrder) -> List<BookOrder> {
    let mut result: List<BookOrder> = []
    let mut placed = false
    for existing in bids {
        if !placed && bid_before(order, existing) {
            result = result.push(order)
            placed = true
        }
        result = result.push(existing)
    }
    if !placed {
        result = result.push(order)
    }
    return result
}

fn insert_ask(asks: List<BookOrder>, order: BookOrder) -> List<BookOrder> {
    let mut result: List<BookOrder> = []
    let mut placed = false
    for existing in asks {
        if !placed && ask_before(order, existing) {
            result = result.push(order)
            placed = true
        }
        result = result.push(existing)
    }
    if !placed {
        result = result.push(order)
    }
    return result
}

fn remove_order_id(orders: List<BookOrder>, id: String) -> List<BookOrder> {
    let mut result: List<BookOrder> = []
    for order in orders {
        if order.id != id {
            result = result.push(order)
        }
    }
    return result
}

fn with_quantity(order: BookOrder, quantity_lots: Int) -> BookOrder {
    return BookOrder {
        id: order.id,
        owner_id: order.owner_id,
        side: order.side,
        price_ticks: order.price_ticks,
        quantity_lots: quantity_lots,
        sequence: order.sequence,
    }
}

fn execute_buy(book: OrderBook, incoming: BookOrder) -> OrderBook {
    let mut remaining = incoming.quantity_lots
    let mut asks: List<BookOrder> = []
    let mut events = book.events

    for resting in book.asks {
        if remaining > 0 && crosses(incoming, resting) {
            let fill = min_int(remaining, resting.quantity_lots)
            events = events.push(TradeExecuted(BookTrade {
                maker_id: resting.id,
                taker_id: incoming.id,
                price_ticks: resting.price_ticks,
                quantity_lots: fill,
                maker_sequence: resting.sequence,
                taker_sequence: incoming.sequence,
            }))
            remaining = remaining - fill
            let maker_remaining = resting.quantity_lots - fill
            if maker_remaining > 0 {
                asks = asks.push(with_quantity(resting, maker_remaining))
            }
        } else {
            asks = asks.push(resting)
        }
    }

    let mut bids = book.bids
    if remaining > 0 {
        bids = insert_bid(bids, with_quantity(incoming, remaining))
    }

    return OrderBook {
        bids: bids,
        asks: asks,
        seen_ids: book.seen_ids,
        last_sequence: book.last_sequence,
        events: events,
    }
}

fn execute_sell(book: OrderBook, incoming: BookOrder) -> OrderBook {
    let mut remaining = incoming.quantity_lots
    let mut bids: List<BookOrder> = []
    let mut events = book.events

    for resting in book.bids {
        if remaining > 0 && crosses(incoming, resting) {
            let fill = min_int(remaining, resting.quantity_lots)
            events = events.push(TradeExecuted(BookTrade {
                maker_id: resting.id,
                taker_id: incoming.id,
                price_ticks: resting.price_ticks,
                quantity_lots: fill,
                maker_sequence: resting.sequence,
                taker_sequence: incoming.sequence,
            }))
            remaining = remaining - fill
            let maker_remaining = resting.quantity_lots - fill
            if maker_remaining > 0 {
                bids = bids.push(with_quantity(resting, maker_remaining))
            }
        } else {
            bids = bids.push(resting)
        }
    }

    let mut asks = book.asks
    if remaining > 0 {
        asks = insert_ask(asks, with_quantity(incoming, remaining))
    }

    return OrderBook {
        bids: bids,
        asks: asks,
        seen_ids: book.seen_ids,
        last_sequence: book.last_sequence,
        events: events,
    }
}

fn execute_incoming(book: OrderBook, incoming: BookOrder) -> OrderBook {
    if incoming.side == Buy() {
        return execute_buy(book, incoming)
    }
    return execute_sell(book, incoming)
}

fn submit_order(book: OrderBook, order: BookOrder, policy: VenuePolicy) -> OrderBook or Error {
    if !valid_new_order(order, policy) {
        return Error("KS3810: order violates venue tick/lot/risk policy")
    }
    if !sequence_is_new(book, order.sequence) {
        return Error("KS3811: order sequence is not strictly monotonic")
    }
    if book.seen_ids.contains(order.id) {
        return Error("KS3812: duplicate order id")
    }
    if !self_trade_preflight(book, order, policy) {
        return Error("KS3813: self-trade policy rejected order")
    }

    let prepared = OrderBook {
        bids: book.bids,
        asks: book.asks,
        seen_ids: book.seen_ids.push(order.id),
        last_sequence: order.sequence,
        events: book.events.push(OrderAccepted(AcceptedEvent {
            order_id: order.id,
            sequence: order.sequence,
        })),
    }
    return execute_incoming(prepared, order)
}

fn cancel_order(book: OrderBook, id: String, sequence: Int) -> OrderBook or Error {
    if !sequence_is_new(book, sequence) {
        return Error("KS3811: cancel sequence is not strictly monotonic")
    }
    if !active_order_exists(book, id) {
        return Error("KS3814: cancel target is not active")
    }

    return OrderBook {
        bids: remove_order_id(book.bids, id),
        asks: remove_order_id(book.asks, id),
        seen_ids: book.seen_ids,
        last_sequence: sequence,
        events: book.events.push(OrderCanceled(CanceledEvent {
            order_id: id,
            sequence: sequence,
        })),
    }
}

fn replace_order(book: OrderBook, id: String, price_ticks: Int, quantity_lots: Int, sequence: Int, policy: VenuePolicy) -> OrderBook or Error {
    if !sequence_is_new(book, sequence) {
        return Error("KS3811: replace sequence is not strictly monotonic")
    }

    let previous = find_active_order(book, id) or return Error("KS3815: replace target is not active")
    let replacement = BookOrder {
        id: previous.id,
        owner_id: previous.owner_id,
        side: previous.side,
        price_ticks: price_ticks,
        quantity_lots: quantity_lots,
        sequence: sequence,
    }
    if !valid_new_order(replacement, policy) {
        return Error("KS3810: replacement violates venue tick/lot/risk policy")
    }

    let trimmed = OrderBook {
        bids: remove_order_id(book.bids, id),
        asks: remove_order_id(book.asks, id),
        seen_ids: book.seen_ids,
        last_sequence: book.last_sequence,
        events: book.events,
    }
    if !self_trade_preflight(trimmed, replacement, policy) {
        return Error("KS3813: self-trade policy rejected replacement")
    }

    let prepared = OrderBook {
        bids: trimmed.bids,
        asks: trimmed.asks,
        seen_ids: trimmed.seen_ids,
        last_sequence: sequence,
        events: trimmed.events.push(OrderReplaced(ReplacedEvent {
            order_id: id,
            previous_sequence: previous.sequence,
            sequence: sequence,
            price_ticks: price_ticks,
            quantity_lots: quantity_lots,
        })),
    }
    return execute_incoming(prepared, replacement)
}

fn main() {
    let policy = VenuePolicy {
        tick_size_ticks: 50,
        lot_size_lots: 1,
        max_order_lots: 1000,
        reject_self_trade: true,
    }
    let mut book = empty_book()

    book = submit_order(book, BookOrder {
        id: "S1",
        owner_id: "maker-a",
        side: Sell(),
        price_ticks: 10100,
        quantity_lots: 5,
        sequence: 1,
    }, policy) or return
    book = submit_order(book, BookOrder {
        id: "S2",
        owner_id: "maker-b",
        side: Sell(),
        price_ticks: 10200,
        quantity_lots: 3,
        sequence: 2,
    }, policy) or return
    book = submit_order(book, BookOrder {
        id: "B1",
        owner_id: "taker-a",
        side: Buy(),
        price_ticks: 10200,
        quantity_lots: 6,
        sequence: 3,
    }, policy) or return
    book = submit_order(book, BookOrder {
        id: "B2",
        owner_id: "bidder-a",
        side: Buy(),
        price_ticks: 10150,
        quantity_lots: 4,
        sequence: 4,
    }, policy) or return
    book = cancel_order(book, "B2", 5) or return
    book = replace_order(book, "S2", 10050, 2, 6, policy) or return
    book = submit_order(book, BookOrder {
        id: "B3",
        owner_id: "taker-b",
        side: Buy(),
        price_ticks: 10100,
        quantity_lots: 1,
        sequence: 7,
    }, policy) or return

    let best_ask = book.asks.get(0) or return
    println(book.bids.length())
    println(book.asks.length())
    println(best_ask.id)
    println(best_ask.price_ticks)
    println(best_ask.quantity_lots)
    println(book.seen_ids.length())
    println(book.last_sequence)
    println(book.events.length())

    let duplicate = submit_order(book, BookOrder {
        id: "B3",
        owner_id: "other",
        side: Buy(),
        price_ticks: 10100,
        quantity_lots: 1,
        sequence: 8,
    }, policy) or {
        println("duplicate-rejected")
        book
    }
    println(duplicate.events.length())

    let mut self_book = empty_book()
    self_book = submit_order(self_book, BookOrder {
        id: "SELF-S",
        owner_id: "same-owner",
        side: Sell(),
        price_ticks: 10000,
        quantity_lots: 1,
        sequence: 1,
    }, policy) or return
    let blocked = submit_order(self_book, BookOrder {
        id: "SELF-B",
        owner_id: "same-owner",
        side: Buy(),
        price_ticks: 10000,
        quantity_lots: 1,
        sequence: 2,
    }, policy) or {
        println("self-trade-rejected")
        self_book
    }
    println(blocked.events.length())
}
