fn send_ten(queue: BoundedQueue<Int>) {
    queue_try_send(queue, 10)
}

fn send_twenty(queue: BoundedQueue<Int>) {
    queue_try_send(queue, 20)
}

fn main() {
    let queue = bounded_queue(2, 0) or return
    let scope = task_scope(2) or return

    let first = task_spawn(scope, send_ten, queue) or -1
    let second = task_spawn(scope, send_twenty, queue) or -1

    println(task_cancel(scope, first) or false)
    println(task_cancel(scope, first) or true)
    println(task_pending(scope))

    task_join_all(scope) or return

    println(task_pending(scope))
    println(queue_try_recv(queue) or -1)
    println(queue_try_recv(queue) or -1)
    println(second)
}
