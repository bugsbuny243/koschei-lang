package parser

import (
	"github.com/bugsbuny243/koschei-lang/native/lexer"
	"github.com/bugsbuny243/koschei-lang/native/syntax"
)

func (parser *Parser) block(depth int) (syntax.Block, error) {
	leftBrace, err := parser.consume(lexer.LEFTBRACE, "expected '{' to start block")
	if err != nil {
		return syntax.Block{}, err
	}
	if err := parser.ensureDepth(depth, leftBrace); err != nil {
		return syntax.Block{}, err
	}
	statements := make([]syntax.Statement, 0)
	for !parser.check(lexer.RIGHTBRACE) && !parser.atEnd() {
		statement, err := parser.statement(depth + 1)
		if err != nil {
			return syntax.Block{}, err
		}
		statements = append(statements, statement)
	}
	if _, err := parser.consume(lexer.RIGHTBRACE, "expected '}' after block"); err != nil {
		return syntax.Block{}, err
	}
	if err := parser.claim(leftBrace); err != nil {
		return syntax.Block{}, err
	}
	return syntax.Block{Kind: "Block", Statements: statements, Location: location(leftBrace)}, nil
}

func (parser *Parser) statement(depth int) (syntax.Statement, error) {
	if err := parser.ensureDepth(depth, parser.peek()); err != nil {
		return syntax.Statement{}, err
	}
	if parser.match(lexer.LET) {
		return parser.letStatement(parser.previous(), depth+1)
	}
	if parser.match(lexer.RETURN) {
		return parser.returnStatement(parser.previous(), depth+1)
	}
	if parser.match(lexer.IF) {
		return parser.ifStatement(parser.previous(), depth+1)
	}
	if parser.match(lexer.WHILE) {
		return parser.whileStatement(parser.previous(), depth+1)
	}
	if parser.match(lexer.FOR) {
		return parser.forStatement(parser.previous(), depth+1)
	}
	if parser.match(lexer.BREAK) {
		return parser.loopControlStatement(parser.previous(), "BreakStatement")
	}
	if parser.match(lexer.CONTINUE) {
		return parser.loopControlStatement(parser.previous(), "ContinueStatement")
	}
	value, err := parser.expression(depth + 1)
	if err != nil {
		return syntax.Statement{}, err
	}
	parser.match(lexer.SEMICOLON)
	start := tokenForExpression(value)
	if err := parser.claim(start); err != nil {
		return syntax.Statement{}, err
	}
	return syntax.Statement{Kind: "ExpressionStatement", Location: value.Location, Expression: &value}, nil
}

func (parser *Parser) letStatement(start lexer.Token, depth int) (syntax.Statement, error) {
	mutable := parser.match(lexer.MUT)
	name, err := parser.consume(lexer.IDENTIFIER, "expected variable name")
	if err != nil {
		return syntax.Statement{}, err
	}
	var annotation *syntax.TypeRef
	if parser.match(lexer.COLON) {
		value, err := parser.typeRef(depth + 1)
		if err != nil {
			return syntax.Statement{}, err
		}
		annotation = &value
	}
	if _, err := parser.consume(lexer.EQUAL, "expected '=' in variable declaration"); err != nil {
		return syntax.Statement{}, err
	}
	value, err := parser.expression(depth)
	if err != nil {
		return syntax.Statement{}, err
	}
	parser.match(lexer.SEMICOLON)
	if err := parser.claim(start); err != nil {
		return syntax.Statement{}, err
	}
	return syntax.Statement{
		Kind: "LetStatement", Location: location(start), Name: name.Value,
		Mutable: boolPointer(mutable), Annotation: annotation, Value: &value,
	}, nil
}

func (parser *Parser) loopControlStatement(start lexer.Token, kind string) (syntax.Statement, error) {
	parser.match(lexer.SEMICOLON)
	if err := parser.claim(start); err != nil {
		return syntax.Statement{}, err
	}
	return syntax.Statement{Kind: kind, Location: location(start)}, nil
}

func (parser *Parser) returnStatement(start lexer.Token, depth int) (syntax.Statement, error) {
	var value *syntax.Expression
	if !orReturnStop(parser.peek().Kind) {
		parsed, err := parser.expression(depth)
		if err != nil {
			return syntax.Statement{}, err
		}
		value = &parsed
	}
	parser.match(lexer.SEMICOLON)
	if err := parser.claim(start); err != nil {
		return syntax.Statement{}, err
	}
	return syntax.Statement{Kind: "ReturnStatement", Location: location(start), Value: value}, nil
}

func (parser *Parser) ifStatement(start lexer.Token, depth int) (syntax.Statement, error) {
	condition, err := parser.expression(depth)
	if err != nil {
		return syntax.Statement{}, err
	}
	thenBlock, err := parser.block(depth + 1)
	if err != nil {
		return syntax.Statement{}, err
	}
	var elseBlock *syntax.Block
	var elseIf *syntax.Statement
	if parser.match(lexer.ELSE) {
		if parser.match(lexer.IF) {
			value, err := parser.ifStatement(parser.previous(), depth+1)
			if err != nil {
				return syntax.Statement{}, err
			}
			elseIf = &value
		} else {
			value, err := parser.block(depth + 1)
			if err != nil {
				return syntax.Statement{}, err
			}
			elseBlock = &value
		}
	}
	if err := parser.claim(start); err != nil {
		return syntax.Statement{}, err
	}
	return syntax.Statement{Kind: "IfStatement", Location: location(start), Condition: &condition, Then: &thenBlock, Else: elseBlock, ElseIf: elseIf}, nil
}

func (parser *Parser) whileStatement(start lexer.Token, depth int) (syntax.Statement, error) {
	condition, err := parser.expression(depth)
	if err != nil {
		return syntax.Statement{}, err
	}
	body, err := parser.block(depth + 1)
	if err != nil {
		return syntax.Statement{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.Statement{}, err
	}
	return syntax.Statement{Kind: "WhileStatement", Location: location(start), Condition: &condition, Body: &body}, nil
}

func (parser *Parser) forStatement(start lexer.Token, depth int) (syntax.Statement, error) {
	variable, err := parser.consume(lexer.IDENTIFIER, "expected loop variable")
	if err != nil {
		return syntax.Statement{}, err
	}
	if _, err := parser.consume(lexer.IN, "expected 'in' after loop variable"); err != nil {
		return syntax.Statement{}, err
	}
	iterable, err := parser.expression(depth)
	if err != nil {
		return syntax.Statement{}, err
	}
	body, err := parser.block(depth + 1)
	if err != nil {
		return syntax.Statement{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.Statement{}, err
	}
	return syntax.Statement{Kind: "ForStatement", Location: location(start), Variable: variable.Value, Iterable: &iterable, Body: &body}, nil
}
