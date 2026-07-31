package parser

import (
	"fmt"

	"github.com/bugsbuny243/koschei-lang/native/syntax"
)

// depthFrame keeps validation iterative. Host recursion is deliberately avoided:
// the validator exists to reject trees that would otherwise make JSON encoding
// recurse beyond the configured syntax-depth budget.
type depthFrame struct {
	expression *syntax.Expression
	statement  *syntax.Statement
	block      *syntax.Block
	depth      int
}

func validateExpressionDepth(document syntax.Document, maxDepth int) error {
	stack := make([]depthFrame, 0, len(document.Functions))
	for index := range document.Functions {
		stack = append(stack, depthFrame{block: &document.Functions[index].Body})
	}

	for len(stack) != 0 {
		last := len(stack) - 1
		frame := stack[last]
		stack = stack[:last]

		switch {
		case frame.expression != nil:
			expression := frame.expression
			depth := frame.depth
			if depth > maxDepth {
				return &Error{
					Line:    expression.Location.Line,
					Column:  expression.Location.Column,
					Message: fmt.Sprintf("parser depth budget exhausted at depth %d", maxDepth),
					Cause:   ErrDepthBudget,
				}
			}
			nextDepth := depth + 1
			pushExpressionChildren(&stack, expression, nextDepth)

		case frame.statement != nil:
			pushStatementChildren(&stack, frame.statement, frame.depth)

		case frame.block != nil:
			for index := len(frame.block.Statements) - 1; index >= 0; index-- {
				stack = append(stack, depthFrame{
					statement: &frame.block.Statements[index],
					depth:     frame.depth,
				})
			}
		}
	}
	return nil
}

func pushStatementChildren(stack *[]depthFrame, statement *syntax.Statement, depth int) {
	if statement.Value != nil {
		*stack = append(*stack, depthFrame{expression: statement.Value, depth: depth + 1})
	}
	if statement.Expression != nil {
		*stack = append(*stack, depthFrame{expression: statement.Expression, depth: depth + 1})
	}
	if statement.Condition != nil {
		*stack = append(*stack, depthFrame{expression: statement.Condition, depth: depth + 1})
	}
	if statement.Iterable != nil {
		*stack = append(*stack, depthFrame{expression: statement.Iterable, depth: depth + 1})
	}
	if statement.Then != nil {
		*stack = append(*stack, depthFrame{block: statement.Then, depth: depth})
	}
	if statement.Else != nil {
		*stack = append(*stack, depthFrame{block: statement.Else, depth: depth})
	}
	if statement.ElseIf != nil {
		*stack = append(*stack, depthFrame{statement: statement.ElseIf, depth: depth})
	}
	if statement.Body != nil {
		*stack = append(*stack, depthFrame{block: statement.Body, depth: depth})
	}
}

func pushExpressionChildren(stack *[]depthFrame, expression *syntax.Expression, depth int) {
	push := func(child *syntax.Expression) {
		if child != nil {
			*stack = append(*stack, depthFrame{expression: child, depth: depth})
		}
	}

	push(expression.Object)
	push(expression.Callee)
	push(expression.Target)
	push(expression.Value)
	push(expression.Left)
	push(expression.Right)
	push(expression.Operand)
	push(expression.Fallback)
	push(expression.Error)

	for index := len(expression.Parts) - 1; index >= 0; index-- {
		push(&expression.Parts[index])
	}
	for index := len(expression.Fields) - 1; index >= 0; index-- {
		push(&expression.Fields[index].Value)
	}
	for index := len(expression.Items) - 1; index >= 0; index-- {
		push(&expression.Items[index])
	}
	for index := len(expression.Entries) - 1; index >= 0; index-- {
		push(&expression.Entries[index].Value)
		push(&expression.Entries[index].Key)
	}
	for index := len(expression.Arguments) - 1; index >= 0; index-- {
		push(&expression.Arguments[index])
	}
	for index := len(expression.Arms) - 1; index >= 0; index-- {
		push(&expression.Arms[index].Body)
	}
	if expression.Handler != nil {
		*stack = append(*stack, depthFrame{block: expression.Handler, depth: depth})
	}
}
