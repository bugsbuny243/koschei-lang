fn main() {
    let queue = bounded_queue(2, 0) or return

    println(queue_try_send(queue, 10))
    println(queue_try_send(queue, 20))
    println(queue_try_send(queue, 30))
    println(queue_len(queue))
    println(queue_capacity(queue))

    let first = queue_try_recv(queue) or -1
    println(first)
    println(queue_try_send(queue, 30))
    let second = queue_try_recv(queue) or -1
    let third = queue_try_recv(queue) or -1
    let empty = queue_try_recv(queue) or -1
    println(second)
    println(third)
    println(empty)
}
