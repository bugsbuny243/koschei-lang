"""Bounded queues, structured task scopes and parallel_map for MIR-Go binaries.

Task scopes are cooperative and deterministic (structured_tasks): spawn only
records work, and task_join_all runs every non-cancelled task in spawn order.
parallel_map maps in input order. So a native binary prints exactly what
`ks run` prints. Results and messages follow the canonical MIR adapters:
bounded_queue_mir_v1, structured_tasks_mir_v1, structured_task_safety_v1 and
deterministic_parallel_map_v1.
"""

from __future__ import annotations

TASK_BUILTINS = {
    "bounded_queue": "_ksQueueNew",
    "queue_try_send": "_ksQueueTrySend",
    "queue_try_recv": "_ksQueueTryRecv",
    "queue_len": "_ksQueueLen",
    "queue_capacity": "_ksQueueCapacity",
    "task_scope": "_ksTaskScopeNew",
    "task_spawn": "_ksTaskSpawn",
    "task_join_all": "_ksTaskJoinAll",
    "task_pending": "_ksTaskPending",
    "task_capacity": "_ksTaskCapacity",
    "task_closed": "_ksTaskClosed",
    "task_cancel": "_ksTaskCancel",
    "task_cancel_all": "_ksTaskCancelAll",
    "parallel_map": "_ksParallelMap",
}
TASK_ARITY = {
    "bounded_queue": 2,
    "queue_try_send": 2,
    "task_spawn": 3,
    "task_cancel": 2,
    "parallel_map": 3,
}
# Builtins whose argument at this position is a named one-parameter worker.
WORKER_ARGUMENT = {"task_spawn": 1, "parallel_map": 1}

TASK_RUNTIME = r"""
func _ksIsCapabilityValue(value any) bool {
	base, _ := _ksGenericType(_ksTypeName(value))
	switch base {
	case "SystemCaps", "NetRoot", "DiskRoot", "EnvRoot", "ProcessRoot", "NetCaps", "DiskCaps",
		"DiskReadCaps", "EnvCaps", "ProcessCaps", "PersistRoot", "PersistCaps", "ServeRoot",
		"ServeCaps", "InputRoot", "InputCaps", "ClockRoot", "ClockCaps", "RandomRoot", "RandomCaps":
		return true
	}
	switch item := value.(type) {
	case []any:
		for _, element := range item {
			if _ksIsCapabilityValue(element) {
				return true
			}
		}
	case _ksMap:
		for _, element := range item.values {
			if _ksIsCapabilityValue(element) {
				return true
			}
		}
	case _ksStruct:
		for _, element := range item.values {
			if _ksIsCapabilityValue(element) {
				return true
			}
		}
	case _ksEnumValue:
		return item.hasPayload && _ksIsCapabilityValue(item.payload)
	}
	return false
}

func _ksIsScalar(value any) bool {
	switch value.(type) {
	case bool, int64, float64, string:
		return true
	}
	return false
}

func _ksQueueNew(capacityValue any, witness any) any {
	if _ksIsCapabilityValue(witness) {
		return _ksError{message: "KS3904: capability values cannot be bounded-queue item types"}
	}
	capacity, ok := capacityValue.(int64)
	if !ok {
		return _ksError{message: "KS3901: queue capacity must be Int"}
	}
	if capacity < 1 || capacity > 65536 {
		return _ksError{message: "KS3901: queue capacity must be between 1 and 65536"}
	}
	return &_ksQueue{capacity: capacity, itemType: _ksTypeName(witness), buffer: make([]any, capacity)}
}

func _ksAsQueue(name string, value any) (*_ksQueue, any) {
	queue, ok := value.(*_ksQueue)
	if !ok {
		return nil, _ksError{message: "KS3902: " + name + " expects BoundedQueue"}
	}
	return queue, nil
}

func _ksQueueTrySend(queueValue any, value any) any {
	queue, failure := _ksAsQueue("queue_try_send", queueValue)
	if failure != nil {
		return failure
	}
	if _ksIsCapabilityValue(value) {
		return _ksError{message: "KS3904: capability values cannot enter a bounded queue"}
	}
	if !_ksMatchesType(value, []string{queue.itemType}, nil, nil) {
		return _ksError{message: "KS3904: bounded-queue runtime item type mismatch: expected " + queue.itemType}
	}
	if queue.count == queue.capacity {
		return false
	}
	queue.buffer[queue.tail] = value
	queue.tail = (queue.tail + 1) % queue.capacity
	queue.count++
	return true
}

func _ksQueueTryRecv(queueValue any) any {
	queue, failure := _ksAsQueue("queue_try_recv", queueValue)
	if failure != nil {
		return failure
	}
	if queue.count == 0 {
		return _ksError{message: "KS3903: bounded queue is empty"}
	}
	value := queue.buffer[queue.head]
	queue.buffer[queue.head] = nil
	queue.head = (queue.head + 1) % queue.capacity
	queue.count--
	return value
}

func _ksQueueLen(queueValue any) any {
	queue, failure := _ksAsQueue("queue_len", queueValue)
	if failure != nil {
		return failure
	}
	return queue.count
}

func _ksQueueCapacity(queueValue any) any {
	queue, failure := _ksAsQueue("queue_capacity", queueValue)
	if failure != nil {
		return failure
	}
	return queue.capacity
}

func _ksTaskScopeNew(capacityValue any) any {
	capacity, ok := capacityValue.(int64)
	if !ok {
		return _ksError{message: "KS3911: task scope capacity must be Int"}
	}
	if capacity < 1 || capacity > 4096 {
		return _ksError{message: "KS3911: task scope capacity must be between 1 and 4096"}
	}
	return &_ksTaskScope{capacity: capacity, records: make([]_ksTaskRecord, 0, capacity)}
}

func _ksAsTaskScope(name string, value any) (*_ksTaskScope, any) {
	scope, ok := value.(*_ksTaskScope)
	if !ok {
		return nil, _ksError{message: "KS3915: " + name + " expects TaskScope"}
	}
	return scope, nil
}

// A task argument must be share-safe (structured_task_safety_v1): a scalar,
// or a queue of scalars. Capabilities fall through to the spawn checks.
func _ksShareSafe(value any) bool {
	if _ksIsScalar(value) {
		return true
	}
	if queue, ok := value.(*_ksQueue); ok {
		switch queue.itemType {
		case "Bool", "Int", "Float", "String":
			return true
		}
	}
	return false
}

func _ksTaskSpawn(scopeValue any, workerValue any, argument any) any {
	capability := _ksIsCapabilityValue(argument)
	if !capability && !_ksShareSafe(argument) {
		return _ksError{message: "KS3917: task argument is not share-safe in structured task v1"}
	}
	scope, failure := _ksAsTaskScope("task_spawn", scopeValue)
	if failure != nil {
		return failure
	}
	worker, ok := workerValue.(_ksCallback)
	if !ok {
		return _ksError{message: "KS3914: task worker must be a unary named function"}
	}
	if capability {
		return _ksError{message: "KS3914: task arguments cannot carry capabilities in v1"}
	}
	if scope.closed {
		return _ksError{message: "KS3913: task scope is already closed"}
	}
	if int64(len(scope.records)) >= scope.capacity {
		return _ksError{message: "KS3912: task scope capacity is exhausted"}
	}
	scope.records = append(scope.records, _ksTaskRecord{worker: worker, argument: argument})
	return int64(len(scope.records) - 1)
}

func _ksTaskJoinAll(scopeValue any) any {
	scope, failure := _ksAsTaskScope("task_join_all", scopeValue)
	if failure != nil {
		return failure
	}
	if scope.joinResult != nil {
		return scope.joinResult
	}
	scope.closed = true
	var first any
	for index := range scope.records {
		record := &scope.records[index]
		if record.state == _ksTaskStateCancelled {
			continue
		}
		record.state = _ksTaskStateRunning
		result := record.worker(record.argument)
		if _, failed := result.(_ksError); failed {
			record.state = _ksTaskStateFailed
			if first == nil {
				first = result
			}
		} else {
			record.state = _ksTaskStateDone
		}
		scope.terminal++
	}
	if first != nil {
		scope.joinResult = first
	} else {
		scope.joinResult = _ksUnit{}
	}
	return scope.joinResult
}

func _ksTaskPending(scopeValue any) any {
	scope, failure := _ksAsTaskScope("task_pending", scopeValue)
	if failure != nil {
		return failure
	}
	return int64(len(scope.records)) - scope.terminal
}

func _ksTaskCapacity(scopeValue any) any {
	scope, failure := _ksAsTaskScope("task_capacity", scopeValue)
	if failure != nil {
		return failure
	}
	return scope.capacity
}

func _ksTaskClosed(scopeValue any) any {
	scope, failure := _ksAsTaskScope("task_closed", scopeValue)
	if failure != nil {
		return failure
	}
	return scope.closed
}

func _ksTaskCancel(scopeValue any, idValue any) any {
	scope, failure := _ksAsTaskScope("task_cancel", scopeValue)
	if failure != nil {
		return failure
	}
	if scope.closed {
		return _ksError{message: "KS3913: task scope is already closed"}
	}
	id, ok := idValue.(int64)
	if !ok || id < 0 || id >= int64(len(scope.records)) {
		return _ksError{message: "KS3916: task id is outside this scope"}
	}
	record := &scope.records[id]
	if record.state != _ksTaskStatePending {
		return false
	}
	record.state = _ksTaskStateCancelled
	scope.terminal++
	return true
}

func _ksTaskCancelAll(scopeValue any) any {
	scope, failure := _ksAsTaskScope("task_cancel_all", scopeValue)
	if failure != nil {
		return failure
	}
	if scope.closed {
		return _ksError{message: "KS3913: task scope is already closed"}
	}
	cancelled := int64(0)
	for index := range scope.records {
		if scope.records[index].state == _ksTaskStatePending {
			scope.records[index].state = _ksTaskStateCancelled
			scope.terminal++
			cancelled++
		}
	}
	return cancelled
}

func _ksParallelMap(valuesValue any, workerValue any, maxWorkers any) any {
	values, ok := valuesValue.([]any)
	if !ok {
		return _ksError{message: "KS3921: parallel_map expects List<scalar>"}
	}
	limit, ok := maxWorkers.(int64)
	if !ok || limit < 1 || limit > 64 {
		return _ksError{message: "KS3920: parallel_map max_workers must be between 1 and 64"}
	}
	for _, item := range values {
		if !_ksIsScalar(item) {
			return _ksError{message: "KS3921: parallel_map input items must be share-safe scalars"}
		}
	}
	worker, ok := workerValue.(_ksCallback)
	if !ok {
		return _ksError{message: "KS3921: parallel_map expects a direct unary worker"}
	}
	results := make([]any, 0, len(values))
	for _, item := range values {
		mapped := worker(item)
		if _, failed := mapped.(_ksError); failed {
			return mapped
		}
		if !_ksIsScalar(mapped) {
			return _ksError{message: "KS3923: parallel worker returned a non-scalar value"}
		}
		results = append(results, mapped)
	}
	return results
}
"""
