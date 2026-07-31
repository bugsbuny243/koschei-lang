package parser

import (
	"github.com/bugsbuny243/koschei-lang/native/lexer"
	"github.com/bugsbuny243/koschei-lang/native/syntax"
)

func (parser *Parser) importDeclaration() (syntax.ImportDeclaration, error) {
	start, err := parser.consume(lexer.IMPORT, "expected 'import'")
	if err != nil {
		return syntax.ImportDeclaration{}, err
	}
	name, err := parser.consume(lexer.IDENTIFIER, "module name must be a lowercase identifier")
	if err != nil {
		return syntax.ImportDeclaration{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.ImportDeclaration{}, err
	}
	return syntax.ImportDeclaration{Kind: "ImportDeclaration", Name: name.Value, Location: location(start)}, nil
}

func (parser *Parser) structDeclaration(depth int) (syntax.StructDeclaration, error) {
	start, err := parser.consume(lexer.STRUCT, "expected 'struct'")
	if err != nil {
		return syntax.StructDeclaration{}, err
	}
	if err := parser.ensureDepth(depth, start); err != nil {
		return syntax.StructDeclaration{}, err
	}
	name, err := parser.consume(lexer.TYPE, "struct name must start with an uppercase letter")
	if err != nil {
		return syntax.StructDeclaration{}, err
	}
	typeParameters, err := parser.typeParameters(depth + 1)
	if err != nil {
		return syntax.StructDeclaration{}, err
	}
	if _, err := parser.consume(lexer.LEFTBRACE, "expected '{' after struct name"); err != nil {
		return syntax.StructDeclaration{}, err
	}
	fields := make([]syntax.StructField, 0)
	for !parser.check(lexer.RIGHTBRACE) && !parser.atEnd() {
		fieldName, err := parser.consume(lexer.IDENTIFIER, "expected struct field name")
		if err != nil {
			return syntax.StructDeclaration{}, err
		}
		if _, err := parser.consume(lexer.COLON, "expected ':' after struct field name"); err != nil {
			return syntax.StructDeclaration{}, err
		}
		fieldType, err := parser.typeRef(depth + 1)
		if err != nil {
			return syntax.StructDeclaration{}, err
		}
		if err := parser.claim(fieldName); err != nil {
			return syntax.StructDeclaration{}, err
		}
		fields = append(fields, syntax.StructField{Name: fieldName.Value, Type: fieldType, Location: location(fieldName)})
		if !parser.match(lexer.COMMA) {
			break
		}
	}
	if _, err := parser.consume(lexer.RIGHTBRACE, "expected '}' after struct fields"); err != nil {
		return syntax.StructDeclaration{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.StructDeclaration{}, err
	}
	return syntax.StructDeclaration{
		Kind: "StructDeclaration", Name: name.Value, TypeParameters: typeParameters,
		Fields: fields, Location: location(start),
	}, nil
}

func (parser *Parser) enumDeclaration(depth int) (syntax.EnumDeclaration, error) {
	start, err := parser.consume(lexer.ENUM, "expected 'enum'")
	if err != nil {
		return syntax.EnumDeclaration{}, err
	}
	if err := parser.ensureDepth(depth, start); err != nil {
		return syntax.EnumDeclaration{}, err
	}
	name, err := parser.consume(lexer.TYPE, "enum name must start with an uppercase letter")
	if err != nil {
		return syntax.EnumDeclaration{}, err
	}
	typeParameters, err := parser.typeParameters(depth + 1)
	if err != nil {
		return syntax.EnumDeclaration{}, err
	}
	if _, err := parser.consume(lexer.LEFTBRACE, "expected '{' after enum name"); err != nil {
		return syntax.EnumDeclaration{}, err
	}
	variants := make([]syntax.EnumVariant, 0)
	for !parser.check(lexer.RIGHTBRACE) && !parser.atEnd() {
		variant, err := parser.consume(lexer.TYPE, "expected enum variant name")
		if err != nil {
			return syntax.EnumDeclaration{}, err
		}
		var payload *syntax.TypeRef
		if parser.match(lexer.LEFTPAREN) {
			value, err := parser.typeRef(depth + 1)
			if err != nil {
				return syntax.EnumDeclaration{}, err
			}
			payload = &value
			if _, err := parser.consume(lexer.RIGHTPAREN, "expected ')' after enum payload type"); err != nil {
				return syntax.EnumDeclaration{}, err
			}
		}
		if err := parser.claim(variant); err != nil {
			return syntax.EnumDeclaration{}, err
		}
		variants = append(variants, syntax.EnumVariant{Name: variant.Value, PayloadType: payload, Location: location(variant)})
		if !parser.match(lexer.COMMA) {
			break
		}
		if parser.check(lexer.RIGHTBRACE) {
			break
		}
	}
	if _, err := parser.consume(lexer.RIGHTBRACE, "expected '}' after enum variants"); err != nil {
		return syntax.EnumDeclaration{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.EnumDeclaration{}, err
	}
	return syntax.EnumDeclaration{
		Kind: "EnumDeclaration", Name: name.Value, TypeParameters: typeParameters,
		Variants: variants, Location: location(start),
	}, nil
}

func (parser *Parser) functionDeclaration(depth int) (syntax.FunctionDeclaration, error) {
	start, err := parser.consume(lexer.FN, "function declaration must start with 'fn'")
	if err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	if err := parser.ensureDepth(depth, start); err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	name, err := parser.consume(lexer.IDENTIFIER, "expected function name")
	if err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	typeParameters, err := parser.typeParameters(depth + 1)
	if err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	if _, err := parser.consume(lexer.LEFTPAREN, "expected '(' after function name"); err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	parameters := make([]syntax.Parameter, 0)
	if !parser.check(lexer.RIGHTPAREN) {
		for {
			parameter, err := parser.parameter(depth + 1)
			if err != nil {
				return syntax.FunctionDeclaration{}, err
			}
			parameters = append(parameters, parameter)
			if !parser.match(lexer.COMMA) {
				break
			}
			if parser.check(lexer.RIGHTPAREN) {
				break
			}
		}
	}
	if _, err := parser.consume(lexer.RIGHTPAREN, "expected ')' after function parameters"); err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	var returnType *syntax.TypeRef
	if parser.match(lexer.ARROW) {
		value, err := parser.typeRef(depth + 1)
		if err != nil {
			return syntax.FunctionDeclaration{}, err
		}
		returnType = &value
	}
	body, err := parser.block(depth + 1)
	if err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	if err := parser.claim(start); err != nil {
		return syntax.FunctionDeclaration{}, err
	}
	return syntax.FunctionDeclaration{
		Kind: "FunctionDeclaration", Name: name.Value, TypeParameters: typeParameters,
		Parameters: parameters, ReturnType: returnType, Body: body, Location: location(start),
	}, nil
}

func (parser *Parser) typeParameters(depth int) ([]syntax.TypeParameter, error) {
	parameters := make([]syntax.TypeParameter, 0)
	if !parser.match(lexer.LESS) {
		return parameters, nil
	}
	if err := parser.ensureDepth(depth, parser.previous()); err != nil {
		return nil, err
	}
	for {
		parameter, err := parser.consume(lexer.TYPE, "type parameter must start with an uppercase letter")
		if err != nil {
			return nil, err
		}
		if err := parser.claim(parameter); err != nil {
			return nil, err
		}
		parameters = append(parameters, syntax.TypeParameter{Name: parameter.Value, Location: location(parameter)})
		if !parser.match(lexer.COMMA) {
			break
		}
	}
	if _, err := parser.consume(lexer.GREATER, "expected '>' after type parameters"); err != nil {
		return nil, err
	}
	return parameters, nil
}

func (parser *Parser) parameter(depth int) (syntax.Parameter, error) {
	name, err := parser.consume(lexer.IDENTIFIER, "expected parameter name")
	if err != nil {
		return syntax.Parameter{}, err
	}
	if _, err := parser.consume(lexer.COLON, "expected ':' after parameter name"); err != nil {
		return syntax.Parameter{}, err
	}
	typeRef, err := parser.typeRef(depth)
	if err != nil {
		return syntax.Parameter{}, err
	}
	if err := parser.claim(name); err != nil {
		return syntax.Parameter{}, err
	}
	return syntax.Parameter{Name: name.Value, Type: typeRef, Location: location(name)}, nil
}

func (parser *Parser) typeRef(depth int) (syntax.TypeRef, error) {
	start := parser.peek()
	if err := parser.ensureDepth(depth, start); err != nil {
		return syntax.TypeRef{}, err
	}
	alternatives := make([]syntax.TypeExpression, 0, 1)
	first, err := parser.typeExpression(depth + 1)
	if err != nil {
		return syntax.TypeRef{}, err
	}
	alternatives = append(alternatives, first)
	for parser.match(lexer.OR) {
		alternative, err := parser.typeExpression(depth + 1)
		if err != nil {
			return syntax.TypeRef{}, err
		}
		alternatives = append(alternatives, alternative)
	}
	if err := parser.claim(start); err != nil {
		return syntax.TypeRef{}, err
	}
	return syntax.TypeRef{Kind: "TypeRef", Alternatives: alternatives, Location: location(start)}, nil
}

func (parser *Parser) typeExpression(depth int) (syntax.TypeExpression, error) {
	start, err := parser.consume(lexer.TYPE, "expected type name")
	if err != nil {
		return syntax.TypeExpression{}, err
	}
	if err := parser.ensureDepth(depth, start); err != nil {
		return syntax.TypeExpression{}, err
	}
	arguments := make([]syntax.TypeExpression, 0)
	if parser.match(lexer.LESS) {
		for {
			argument, err := parser.typeExpression(depth + 1)
			if err != nil {
				return syntax.TypeExpression{}, err
			}
			arguments = append(arguments, argument)
			if !parser.match(lexer.COMMA) {
				break
			}
		}
		if _, err := parser.consume(lexer.GREATER, "expected '>' after generic type arguments"); err != nil {
			return syntax.TypeExpression{}, err
		}
	}
	if err := parser.claim(start); err != nil {
		return syntax.TypeExpression{}, err
	}
	return syntax.TypeExpression{Name: start.Value, Arguments: arguments}, nil
}
