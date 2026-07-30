package parser

import (
	"fmt"

	"github.com/bugsbuny243/koschei-lang/native/lexer"
	"github.com/bugsbuny243/koschei-lang/native/syntax"
)

func (parser *Parser) expression(depth int) (syntax.Expression, error) {
	if err := parser.ensureDepth(depth, parser.peek()); err != nil {
		return syntax.Expression{}, err
	}
	return parser.assignment(depth)
}

func (parser *Parser) assignment(depth int) (syntax.Expression, error) {
	expression, err := parser.orHandler(depth)
	if err != nil {
		return syntax.Expression{}, err
	}
	if parser.match(lexer.EQUAL) {
		equals := parser.previous()
		value, err := parser.assignment(depth + 1)
		if err != nil {
			return syntax.Expression{}, err
		}
		if expression.Kind != "Identifier" && expression.Kind != "MemberExpression" {
			return syntax.Expression{}, parser.failure(equals, "invalid assignment target", nil)
		}
		if err := parser.claim(equals); err != nil {
			return syntax.Expression{}, err
		}
		targetCopy, valueCopy := expression, value
		return syntax.Expression{Kind: "AssignmentExpression", Location: location(equals), Target: &targetCopy, Value: &valueCopy}, nil
	}
	return expression, nil
}

func (parser *Parser) orHandler(depth int) (syntax.Expression, error) {
	expression, err := parser.logicalOr(depth)
	if err != nil {
		return syntax.Expression{}, err
	}
	for parser.match(lexer.OR) {
		operator := parser.previous()
		if parser.match(lexer.RETURN) {
			var failureExpression *syntax.Expression
			if !orReturnStop(parser.peek().Kind) {
				value, err := parser.logicalOr(depth + 1)
				if err != nil {
					return syntax.Expression{}, err
				}
				failureExpression = &value
			}
			if err := parser.claim(operator); err != nil {
				return syntax.Expression{}, err
			}
			valueCopy := expression
			expression = syntax.Expression{Kind: "OrReturnExpression", Location: location(operator), Value: &valueCopy, Error: failureExpression}
			continue
		}
		if parser.check(lexer.LEFTBRACE) {
			handler, err := parser.block(depth + 1)
			if err != nil {
				return syntax.Expression{}, err
			}
			if err := parser.claim(operator); err != nil {
				return syntax.Expression{}, err
			}
			valueCopy := expression
			expression = syntax.Expression{Kind: "OrBlockExpression", Location: location(operator), Value: &valueCopy, Handler: &handler}
			continue
		}
		fallback, err := parser.logicalOr(depth + 1)
		if err != nil {
			return syntax.Expression{}, err
		}
		if err := parser.claim(operator); err != nil {
			return syntax.Expression{}, err
		}
		valueCopy, fallbackCopy := expression, fallback
		expression = syntax.Expression{Kind: "OrElseExpression", Location: location(operator), Value: &valueCopy, Fallback: &fallbackCopy}
	}
	return expression, nil
}

func (parser *Parser) logicalOr(depth int) (syntax.Expression, error) {
	return parser.leftAssociative(depth, parser.logicalAnd, []lexer.Kind{lexer.PIPEPIPE})
}

func (parser *Parser) logicalAnd(depth int) (syntax.Expression, error) {
	return parser.leftAssociative(depth, parser.equality, []lexer.Kind{lexer.AMPAMP})
}

func (parser *Parser) equality(depth int) (syntax.Expression, error) {
	return parser.leftAssociative(depth, parser.comparison, []lexer.Kind{lexer.EQUALEQUAL, lexer.BANGEQUAL})
}

func (parser *Parser) comparison(depth int) (syntax.Expression, error) {
	return parser.leftAssociative(depth, parser.term, []lexer.Kind{lexer.LESS, lexer.LESSEQUAL, lexer.GREATER, lexer.GREATEREQUAL})
}

func (parser *Parser) term(depth int) (syntax.Expression, error) {
	return parser.leftAssociative(depth, parser.factor, []lexer.Kind{lexer.PLUS, lexer.MINUS})
}

func (parser *Parser) factor(depth int) (syntax.Expression, error) {
	return parser.leftAssociative(depth, parser.unary, []lexer.Kind{lexer.STAR, lexer.SLASH})
}

type expressionParser func(int) (syntax.Expression, error)

func (parser *Parser) leftAssociative(depth int, operand expressionParser, operators []lexer.Kind) (syntax.Expression, error) {
	expression, err := operand(depth)
	if err != nil {
		return syntax.Expression{}, err
	}
	for parser.match(operators...) {
		operator := parser.previous()
		right, err := operand(depth)
		if err != nil {
			return syntax.Expression{}, err
		}
		if err := parser.claim(operator); err != nil {
			return syntax.Expression{}, err
		}
		leftCopy, rightCopy := expression, right
		expression = syntax.Expression{
			Kind: "BinaryExpression", Location: location(operator), Operator: operatorText(operator),
			Left: &leftCopy, Right: &rightCopy,
		}
	}
	return expression, nil
}

func (parser *Parser) unary(depth int) (syntax.Expression, error) {
	if parser.match(lexer.BANG, lexer.MINUS) {
		operator := parser.previous()
		operand, err := parser.unary(depth + 1)
		if err != nil {
			return syntax.Expression{}, err
		}
		if err := parser.claim(operator); err != nil {
			return syntax.Expression{}, err
		}
		operandCopy := operand
		return syntax.Expression{Kind: "UnaryExpression", Location: location(operator), Operator: operatorText(operator), Operand: &operandCopy}, nil
	}
	return parser.call(depth)
}

func (parser *Parser) call(depth int) (syntax.Expression, error) {
	expression, err := parser.primary(depth)
	if err != nil {
		return syntax.Expression{}, err
	}
	for {
		if parser.match(lexer.LEFTPAREN) {
			leftParen := parser.previous()
			arguments := make([]syntax.Expression, 0)
			if !parser.check(lexer.RIGHTPAREN) {
				for {
					argument, err := parser.expression(depth + 1)
					if err != nil {
						return syntax.Expression{}, err
					}
					arguments = append(arguments, argument)
					if !parser.match(lexer.COMMA) {
						break
					}
					if parser.check(lexer.RIGHTPAREN) {
						break
					}
				}
			}
			if _, err := parser.consume(lexer.RIGHTPAREN, "expected ')' after call arguments"); err != nil {
				return syntax.Expression{}, err
			}
			if err := parser.claim(leftParen); err != nil {
				return syntax.Expression{}, err
			}
			calleeCopy := expression
			expression = syntax.Expression{Kind: "CallExpression", Location: location(leftParen), Callee: &calleeCopy, Arguments: arguments}
			continue
		}
		if parser.match(lexer.DOT) {
			member, err := parser.consume(lexer.IDENTIFIER, "expected field or method name after '.'")
			if err != nil {
				return syntax.Expression{}, err
			}
			if err := parser.claim(member); err != nil {
				return syntax.Expression{}, err
			}
			objectCopy := expression
			expression = syntax.Expression{Kind: "MemberExpression", Location: location(member), Object: &objectCopy, Member: member.Value}
			continue
		}
		break
	}
	return expression, nil
}

func (parser *Parser) primary(depth int) (syntax.Expression, error) {
	if err := parser.ensureDepth(depth, parser.peek()); err != nil {
		return syntax.Expression{}, err
	}
	if parser.match(lexer.MATCH) {
		return parser.matchExpression(parser.previous(), depth+1)
	}
	if parser.match(lexer.STRING) {
		token := parser.previous()
		return parser.literal(token, syntax.LiteralValue{Kind: "string", Text: stringPointer(token.Value)})
	}
	if parser.match(lexer.NUMBER) {
		token := parser.previous()
		return parser.literal(token, syntax.LiteralValue{Kind: "number", Text: stringPointer(token.Value)})
	}
	if parser.match(lexer.TRUE, lexer.FALSE) {
		token := parser.previous()
		value := token.Kind == lexer.TRUE
		return parser.literal(token, syntax.LiteralValue{Kind: "bool", Bool: &value})
	}
	if parser.match(lexer.STRINGINTERP) {
		return parser.interpolatedString(parser.previous(), depth+1)
	}
	if parser.match(lexer.LEFTBRACKET) {
		return parser.listLiteral(parser.previous(), depth+1)
	}
	if parser.match(lexer.LEFTBRACE) {
		return parser.mapLiteral(parser.previous(), depth+1)
	}
	if parser.match(lexer.IDENTIFIER, lexer.TYPE) {
		token := parser.previous()
		if token.Kind == lexer.TYPE && parser.check(lexer.LEFTBRACE) {
			return parser.structLiteral(token, depth+1)
		}
		if err := parser.claim(token); err != nil {
			return syntax.Expression{}, err
		}
		return syntax.Expression{Kind: "Identifier", Location: location(token), Name: token.Value}, nil
	}
	if parser.match(lexer.LEFTPAREN) {
		expression, err := parser.expression(depth + 1)
		if err != nil {
			return syntax.Expression{}, err
		}
		if _, err := parser.consume(lexer.RIGHTPAREN, "expected ')' after expression"); err != nil {
			return syntax.Expression{}, err
		}
		return expression, nil
	}
	return syntax.Expression{}, parser.failure(parser.peek(), "expected expression", nil)
}

func (parser *Parser) literal(token lexer.Token, value syntax.LiteralValue) (syntax.Expression, error) {
	if err := parser.claim(token); err != nil {
		return syntax.Expression{}, err
	}
	return syntax.Expression{Kind: "Literal", Location: location(token), Literal: &value}, nil
}

func (parser *Parser) listLiteral(start lexer.Token, depth int) (syntax.Expression, error) {
	items := make([]syntax.Expression, 0)
	if !parser.check(lexer.RIGHTBRACKET) {
		for {
			item, err := parser.expression(depth)
			if err != nil {
				return syntax.Expression{}, err
			}
			items = append(items, item)
			if !parser.match(lexer.COMMA) {
				break
			}
			if parser.check(lexer.RIGHTBRACKET) {
				break
			}
		}
	}
	if _, err := parser.consume(lexer.RIGHTBRACKET, "expected ']' after list literal"); err != nil {
		return syntax.Expression{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.Expression{}, err
	}
	return syntax.Expression{Kind: "ListLiteral", Location: location(start), Items: items}, nil
}

func (parser *Parser) mapLiteral(start lexer.Token, depth int) (syntax.Expression, error) {
	entries := make([]syntax.MapEntry, 0)
	if !parser.check(lexer.RIGHTBRACE) {
		for {
			key, err := parser.expression(depth)
			if err != nil {
				return syntax.Expression{}, err
			}
			colon, err := parser.consume(lexer.COLON, "expected ':' after map key")
			if err != nil {
				return syntax.Expression{}, err
			}
			value, err := parser.expression(depth)
			if err != nil {
				return syntax.Expression{}, err
			}
			if err := parser.claim(colon); err != nil {
				return syntax.Expression{}, err
			}
			entries = append(entries, syntax.MapEntry{Key: key, Value: value})
			if !parser.match(lexer.COMMA) {
				break
			}
			if parser.check(lexer.RIGHTBRACE) {
				break
			}
		}
	}
	if _, err := parser.consume(lexer.RIGHTBRACE, "expected '}' after map literal"); err != nil {
		return syntax.Expression{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.Expression{}, err
	}
	return syntax.Expression{Kind: "MapLiteral", Location: location(start), Entries: entries}, nil
}

func (parser *Parser) structLiteral(typeToken lexer.Token, depth int) (syntax.Expression, error) {
	if _, err := parser.consume(lexer.LEFTBRACE, "expected '{' after struct type"); err != nil {
		return syntax.Expression{}, err
	}
	fields := make([]syntax.NamedExpression, 0)
	for !parser.check(lexer.RIGHTBRACE) && !parser.atEnd() {
		name, err := parser.consume(lexer.IDENTIFIER, "expected struct literal field name")
		if err != nil {
			return syntax.Expression{}, err
		}
		if _, err := parser.consume(lexer.COLON, "expected ':' after struct literal field name"); err != nil {
			return syntax.Expression{}, err
		}
		value, err := parser.expression(depth)
		if err != nil {
			return syntax.Expression{}, err
		}
		if err := parser.claim(name); err != nil {
			return syntax.Expression{}, err
		}
		fields = append(fields, syntax.NamedExpression{Name: name.Value, Value: value})
		if !parser.match(lexer.COMMA) {
			break
		}
	}
	if _, err := parser.consume(lexer.RIGHTBRACE, "expected '}' after struct literal"); err != nil {
		return syntax.Expression{}, err
	}
	if err := parser.claim(typeToken); err != nil {
		return syntax.Expression{}, err
	}
	return syntax.Expression{Kind: "StructLiteral", Location: location(typeToken), TypeName: typeToken.Value, Fields: fields}, nil
}

func (parser *Parser) matchExpression(start lexer.Token, depth int) (syntax.Expression, error) {
	value, err := parser.expression(depth)
	if err != nil {
		return syntax.Expression{}, err
	}
	if _, err := parser.consume(lexer.LEFTBRACE, "expected '{' after match value"); err != nil {
		return syntax.Expression{}, err
	}
	arms := make([]syntax.MatchArm, 0)
	for !parser.check(lexer.RIGHTBRACE) && !parser.atEnd() {
		variant, err := parser.consume(lexer.TYPE, "expected variant name in match arm")
		if err != nil {
			return syntax.Expression{}, err
		}
		binding := ""
		if parser.match(lexer.LEFTPAREN) {
			name, err := parser.consume(lexer.IDENTIFIER, "expected payload binding name")
			if err != nil {
				return syntax.Expression{}, err
			}
			binding = name.Value
			if _, err := parser.consume(lexer.RIGHTPAREN, "expected ')' after match binding"); err != nil {
				return syntax.Expression{}, err
			}
		}
		if _, err := parser.consume(lexer.FATARROW, "expected '=>' in match arm"); err != nil {
			return syntax.Expression{}, err
		}
		body, err := parser.expression(depth + 1)
		if err != nil {
			return syntax.Expression{}, err
		}
		if err := parser.claim(variant); err != nil {
			return syntax.Expression{}, err
		}
		arms = append(arms, syntax.MatchArm{Variant: variant.Value, Binding: binding, Body: body, Location: location(variant)})
		if !parser.match(lexer.COMMA) {
			break
		}
		if parser.check(lexer.RIGHTBRACE) {
			break
		}
	}
	if _, err := parser.consume(lexer.RIGHTBRACE, "expected '}' after match arms"); err != nil {
		return syntax.Expression{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.Expression{}, err
	}
	valueCopy := value
	return syntax.Expression{Kind: "MatchExpression", Location: location(start), Value: &valueCopy, Arms: arms}, nil
}

func (parser *Parser) interpolatedString(start lexer.Token, depth int) (syntax.Expression, error) {
	parts := make([]syntax.Expression, 0, len(start.Segments))
	for _, segment := range start.Segments {
		switch segment.Kind {
		case "text":
			part, err := parser.literal(start, syntax.LiteralValue{Kind: "string", Text: stringPointer(segment.Value)})
			if err != nil {
				return syntax.Expression{}, err
			}
			parts = append(parts, part)
		case "expr":
			remainingBytes := parser.budget.config.MaxInterpolationBytes - parser.budget.interpolationBytes
			if remainingBytes < 1 || len(segment.Value) > remainingBytes {
				return syntax.Expression{}, parser.failure(start, fmt.Sprintf("total interpolation byte budget exhausted at %d bytes", parser.budget.config.MaxInterpolationBytes), ErrNodeBudget)
			}
			remainingTokens := parser.budget.config.MaxInterpolationTokens - parser.budget.interpolationTokens
			if remainingTokens < 1 {
				return syntax.Expression{}, parser.failure(start, fmt.Sprintf("total interpolation token budget exhausted at %d tokens", parser.budget.config.MaxInterpolationTokens), ErrNodeBudget)
			}
			tokens, err := lexer.Tokenize(segment.Value, lexer.Config{
				MaxSourceBytes: remainingBytes,
				MaxTokens:      remainingTokens,
			})
			if err != nil {
				return syntax.Expression{}, parser.failure(start, fmt.Sprintf("invalid interpolation expression: %v", err), err)
			}
			parser.budget.interpolationBytes += len(segment.Value)
			parser.budget.interpolationTokens += len(tokens)
			nested := &Parser{tokens: tokens, budget: parser.budget}
			part, err := nested.expression(depth + 1)
			if err != nil {
				return syntax.Expression{}, parser.failure(start, fmt.Sprintf("invalid interpolation expression: %v", err), err)
			}
			if !nested.atEnd() {
				return syntax.Expression{}, parser.failure(start, "interpolation must contain exactly one expression", ErrTokenStream)
			}
			parts = append(parts, part)
		default:
			return syntax.Expression{}, parser.failure(start, fmt.Sprintf("unknown interpolation segment kind %q", segment.Kind), ErrTokenStream)
		}
	}
	if err := parser.claim(start); err != nil {
		return syntax.Expression{}, err
	}
	return syntax.Expression{Kind: "InterpolatedString", Location: location(start), Parts: parts}, nil
}
