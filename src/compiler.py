import sys
from enum import Enum
from typing import Any

import chunk
import debug
import scanner
import value

UINT8_MAX = 256
UINT16_MAX = 65536
UINT8_COUNT = UINT8_MAX + 1

# yapf: disable
rule_map = {
    "TOKEN_LEFT_PAREN":    ["grouping", "call",   "PREC_CALL"],
    "TOKEN_RIGHT_PAREN":   [None,       None,     "PREC_NONE"],
    "TOKEN_LEFT_BRACE":    [None,       None,     "PREC_NONE"],
    "TOKEN_RIGHT_BRACE":   [None,       None,     "PREC_NONE"],
    "TOKEN_COMMA":         [None,       None,     "PREC_NONE"],
    "TOKEN_DOT":           [None,       None,     "PREC_NONE"],
    "TOKEN_MINUS":         ["unary",    "binary", "PREC_TERM"],
    "TOKEN_PLUS":          [None,       "binary", "PREC_TERM"],
    "TOKEN_SEMICOLON":     [None,       None,     "PREC_NONE"],
    "TOKEN_SLASH":         [None,       "binary", "PREC_FACTOR"],
    "TOKEN_STAR":          [None,       "binary", "PREC_FACTOR"],
    "TOKEN_BANG":          ["unary",    None,     "PREC_NONE"],
    "TOKEN_BANG_EQUAL":    [None,       "binary", "PREC_EQUALITY"],
    "TOKEN_EQUAL":         [None,       None,     "PREC_NONE"],
    "TOKEN_EQUAL_EQUAL":   [None,       "binary", "PREC_EQUALITY"],
    "TOKEN_GREATER":       [None,       "binary", "PREC_COMPARISON"],
    "TOKEN_GREATER_EQUAL": [None,       "binary", "PREC_COMPARISON"],
    "TOKEN_LESS":          [None,       "binary", "PREC_COMPARISON"],
    "TOKEN_LESS_EQUAL":    [None,       "binary", "PREC_COMPARISON"],
    "TOKEN_IDENTIFIER":    ["variable", None,     "PREC_NONE"],
    "TOKEN_STRING":        ["string",   None,     "PREC_NONE"],
    "TOKEN_NUMBER":        ["number",   None,     "PREC_NONE"],
    "TOKEN_AND":           [None,       "and_op", "PREC_AND"],
    "TOKEN_CLASS":         [None,       None,     "PREC_NONE"],
    "TOKEN_ELSE":          [None,       None,     "PREC_NONE"],
    "TOKEN_FALSE":         ["literal",  None,     "PREC_NONE"],
    "TOKEN_FOR":           [None,       None,     "PREC_NONE"],
    "TOKEN_FUN":           [None,       None,     "PREC_NONE"],
    "TOKEN_IF":            [None,       None,     "PREC_NONE"],
    "TOKEN_NIL":           ["literal",  None,     "PREC_NONE"],
    "TOKEN_OR":            [None,       "or_op",  "PREC_OR"],
    "TOKEN_PRINT":         [None,       None,     "PREC_NONE"],
    "TOKEN_RETURN":        [None,       None,     "PREC_NONE"],
    "TOKEN_SUPER":         [None,       None,     "PREC_NONE"],
    "TOKEN_THIS":          [None,       None,     "PREC_NONE"],
    "TOKEN_TRUE":          ["literal",  None,     "PREC_NONE"],
    "TOKEN_VAR":           [None,       None,     "PREC_NONE"],
    "TOKEN_WHILE":         [None,       None,     "PREC_NONE"],
    "TOKEN_ERROR":         [None,       None,     "PREC_NONE"],
    "TOKEN_EOF":           [None,       None,     "PREC_NONE"],
}


class Precedence(Enum):
    PREC_NONE = 1
    PREC_ASSIGNMENT = 2  # =
    PREC_OR = 3          # or
    PREC_AND = 4         # and
    PREC_EQUALITY = 5    # == !=
    PREC_COMPARISON = 6  # < > <= >=
    PREC_TERM = 7        # + -
    PREC_FACTOR = 8      # * /
    PREC_UNARY = 9       # ! -
    PREC_CALL = 10       # . ()
    PREC_PRIMARY = 11
# yapf: enable


class ParseRule():
    def __init__(self, prefix, infix, precedence):
        #
        """
        """
        self.prefix = prefix
        self.infix = infix
        self.precedence = precedence


class Local():
    def __init__(self):
        #
        """
        """
        self.name = scanner.Token()
        self.depth = 0


class FunctionType(Enum):
    TYPE_FUNCTION = "TYPE_FUNCTION"
    TYPE_SCRIPT = "TYPE_SCRIPT"


class Compiler():
    def __init__(self, function_type, enclosing):
        #
        """
        """
        self.enclosing = enclosing
        self.function = None
        self.function_type = function_type
        self.locals = [Local() for _ in range(UINT8_COUNT)]  # type: List[Local]
        self.local_count = 0
        self.scope_depth = 0

        # Initialization of bytecode to avoid circular dependency
        self.function = value.new_function()
        self.function.bytecode = chunk.Chunk()

        self.local = self.locals[self.local_count]
        self.local_count += 1
        self.local.name.start = ""
        self.local.name.length = 0


class Parser():
    def __init__(self, reader, composer, bytecode, debug_level):
        # type: (scanner.Scanner, Compiler, chunk.Chunk, bool) -> None
        """
        """
        self.reader = reader
        self.composer = composer
        self.enclosing = composer
        self.bytecode = bytecode  # referred to in text as compiling_chunk
        self.current = None  # type: scanner.Token
        self.previous = None  # type: scanner.Token
        self.had_error = False
        self.panic_mode = False
        self.debug_level = debug_level

    def current_chunk(self):
        #
        """
        """
        return self.composer.function.bytecode

    def error_at(self, token, message):
        #
        """
        """
        if self.panic_mode:
            return None

        self.panic_mode = True

        print("[line {}] Error".format(token.line), end=" ")

        if token.token_type == scanner.TokenType.TOKEN_EOF:
            print(" at end", end=" ")
        elif token.token_type == scanner.TokenType.TOKEN_ERROR:
            pass
        else:
            current_token = self.reader.source[token.start:(token.start + token.length)]
            print("at {}".format(current_token), end="")

        print(": {}".format(message))
        self.had_error = True

    def error(self, message):
        #
        """
        """
        self.error_at(self.previous, message)

    def error_at_current(self, message):
        #
        """
        """
        self.error_at(self.current, message)

    def advance(self):
        # type: () -> None
        """
        """
        self.previous = self.current

        while True:
            self.current = self.reader.scan_token()

            if self.debug_level >= 2 and self.current.token_type:
                print(self.current.token_type)

            if self.current.token_type != scanner.TokenType.TOKEN_ERROR:
                break

            self.error_at_current(self.current.start)

    def consume(self, token_type, message):
        # type: (scanner.TokenType, str) -> None
        """
        """
        if self.current.token_type == token_type:
            self.advance()
            return None

        self.error_at_current(message)

    def check(self, token_type):
        #
        """
        """
        return self.current.token_type == token_type

    def match(self, token_type):
        #
        """
        """
        if not self.check(token_type):
            return False

        self.advance()
        return True

    def emit_byte(self, byte):
        #
        """
        """
        self.current_chunk().write_chunk(byte, self.previous.line)

    def emit_bytes(self, byte1, byte2):
        #
        """
        """
        self.emit_byte(byte1)
        self.emit_byte(byte2)

    def emit_loop(self, loop_start):
        #
        """
        """
        self.emit_byte(chunk.OpCode.OP_LOOP)

        offset = self.current_chunk().count - loop_start + 2

        if offset > UINT16_MAX:
            self.error("Loop body too large.")

        self.emit_byte((offset >> 8) & 0xff)
        self.emit_byte(offset & 0xff)

    def emit_jump(self, instruction):
        #
        """
        """
        self.emit_byte(instruction)
        self.emit_byte(0xff)
        self.emit_byte(0xff)

        return self.current_chunk().count - 2

    def emit_return(self):
        #
        """
        """
        self.emit_byte(chunk.OpCode.OP_NIL)
        self.emit_byte(chunk.OpCode.OP_RETURN)

    def make_constant(self, val):
        #
        """
        """
        constant = self.current_chunk().add_constant(val)

        if constant > UINT8_MAX:
            self.error("Too many constants in one chunk.")
            return None

        return constant

    def emit_constant(self, val):
        #
        """
        """
        self.emit_bytes(chunk.OpCode.OP_CONSTANT, self.make_constant(val))

    def patch_jump(self, offset):
        #
        """
        """
        # -2 to adust for the bytecode for the jump offset itself
        jump = self.current_chunk().count - offset - 2

        if jump > UINT16_MAX:
            self.error("Too much code to jump over")

        self.current_chunk().code[offset] = jump >> 8 & 0xff
        self.current_chunk().code[offset + 1] = jump & 0xff

    def end_compiler(self):
        #
        """
        """
        self.emit_return()
        function = self.composer.function

        if self.debug_level >= 1 and not self.had_error:
            function_name = function.name or "<script>"
            debug.disassemble_chunk(self.current_chunk(), function_name)

        self.composer = self.enclosing
        return function

    def begin_scope(self):
        #
        """
        """
        self.composer.scope_depth += 1

    def end_scope(self):
        #
        """
        """
        self.composer.scope_depth -= 1

        while (self.composer.local_count > 0
               and self.composer.locals[self.composer.local_count - 1].depth >
               self.composer.scope_depth):
            self.emit_byte(chunk.OpCode.OP_POP)
            self.composer.local_count -= 1

    def identifier_constant(self, name):
        #
        """
        """
        chars = name.source[:name.length]
        obj_val = value.obj_val(value.copy_string(chars, name.length))
        return self.make_constant(obj_val)

    @staticmethod
    def identifiers_equal(a, b):
        #
        """
        """
        if not a or not b or a.length != b.length:
            return False

        return a.source == b.source

    def resolve_local(self, name):
        #
        """
        """
        if self.debug_level >= 3:
            print("  {}".format(sys._getframe().f_code.co_name))

        for i in range(self.composer.local_count - 1, -1, -1):
            local = self.composer.locals[i]

            if self.identifiers_equal(name, local.name):
                if local.depth == -1:
                    self.error("Cannot read local variable in its own initializer.")

                return i

        return -1

    def add_local(self, name):
        #
        """
        """
        if self.debug_level >= 3:
            print("  {}".format(sys._getframe().f_code.co_name))

        if self.composer.local_count == UINT8_COUNT:
            self.error("Too many local variables in function.")
            return None

        local = self.composer.locals[self.composer.local_count]
        self.composer.local_count += 1

        local.name = name
        local.depth = -1

    def declare_variable(self):
        #
        """
        """
        if self.debug_level >= 3:
            print("  {}".format(sys._getframe().f_code.co_name))

        # Global variables are implicitly declared
        if self.composer.scope_depth == 0:
            return None

        name = self.previous

        for i in range(self.composer.local_count - 1, -1, -1):
            local = self.composer.locals[i]

            if local.depth != -1 and local.depth < self.composer.scope_depth:
                break

            if self.identifiers_equal(name, local.name):
                self.error("Variable with this name already declared in this scope.")

        self.add_local(name)

    def parse_variable(self, error_message):
        #
        """
        """
        if self.debug_level >= 3:
            print("  {}".format(sys._getframe().f_code.co_name))

        self.consume(scanner.TokenType.TOKEN_IDENTIFIER, error_message)
        self.declare_variable()

        if self.composer.scope_depth > 0:
            return 0

        return self.identifier_constant(self.previous)

    def mark_initialized(self):
        #
        """
        """
        if self.composer.scope_depth == 0:
            return None

        local_count = self.composer.local_count - 1
        self.composer.locals[local_count].depth = self.composer.scope_depth

    def define_variable(self, global_var):
        #
        """
        """
        if self.debug_level >= 3:
            print("  {}".format(sys._getframe().f_code.co_name))

        if self.composer.scope_depth > 0:
            self.mark_initialized()
            return None

        self.emit_bytes(chunk.OpCode.OP_DEFINE_GLOBAL, global_var)

    def argument_list(self):
        # type: () -> int
        """
        """
        arg_count = 0

        if not self.check(scanner.TokenType.TOKEN_RIGHT_PAREN):
            while True:
                self.expression()

                if arg_count == 255:
                    self.error("Cannot have more than 255 arguments.")

                arg_count += 1

                if not self.match(scanner.TokenType.TOKEN_COMMA):
                    break

        self.consume(scanner.TokenType.TOKEN_RIGHT_PAREN, "Expect ')' after arguments.")
        return arg_count

    def and_op(self, can_assign):
        #
        """
        """
        end_jump = self.emit_jump(chunk.OpCode.OP_JUMP_IF_FALSE)

        self.emit_byte(chunk.OpCode.OP_POP)
        self.parse_precedence(Precedence.PREC_AND)

        self.patch_jump(end_jump)

    def binary(self, can_assign):
        #
        """
        """
        # Remember the operator
        operator_type = self.previous.token_type

        # Compile the right operand.
        rule = self.get_rule(operator_type)

        # Get precedence which has 1 priority level above precedence of current rule
        precedence = Precedence(rule.precedence.value + 1)
        self.parse_precedence(precedence)

        if operator_type == scanner.TokenType.TOKEN_BANG_EQUAL:
            self.emit_bytes(chunk.OpCode.OP_EQUAL, chunk.OpCode.OP_NOT)
        elif operator_type == scanner.TokenType.TOKEN_EQUAL_EQUAL:
            self.emit_byte(chunk.OpCode.OP_EQUAL)
        elif operator_type == scanner.TokenType.TOKEN_GREATER:
            self.emit_byte(chunk.OpCode.OP_GREATER)
        elif operator_type == scanner.TokenType.TOKEN_GREATER_EQUAL:
            self.emit_bytes(chunk.OpCode.OP_LESS, chunk.OpCode.OP_NOT)
        elif operator_type == scanner.TokenType.TOKEN_LESS:
            self.emit_byte(chunk.OpCode.OP_LESS)
        elif operator_type == scanner.TokenType.TOKEN_LESS_EQUAL:
            self.emit_bytes(chunk.OpCode.OP_GREATER, chunk.OpCode.OP_NOT)
        elif operator_type == scanner.TokenType.TOKEN_PLUS:
            self.emit_byte(chunk.OpCode.OP_ADD)
        elif operator_type == scanner.TokenType.TOKEN_MINUS:
            self.emit_byte(chunk.OpCode.OP_SUBTRACT)
        elif operator_type == scanner.TokenType.TOKEN_STAR:
            self.emit_byte(chunk.OpCode.OP_MULTIPLY)
        elif operator_type == scanner.TokenType.TOKEN_SLASH:
            self.emit_byte(chunk.OpCode.OP_DIVIDE)

    def call(self, can_assign):
        # type: (bool) -> None
        """
        """
        arg_count = self.argument_list()
        self.emit_bytes(chunk.OpCode.OP_CALL, arg_count)

    def literal(self, can_assign):
        #
        """
        """
        if self.previous.token_type == scanner.TokenType.TOKEN_FALSE:
            self.emit_byte(chunk.OpCode.OP_FALSE)
        elif self.previous.token_type == scanner.TokenType.TOKEN_NIL:
            self.emit_byte(chunk.OpCode.OP_NIL)
        elif self.previous.token_type == scanner.TokenType.TOKEN_TRUE:
            self.emit_byte(chunk.OpCode.OP_TRUE)

    def grouping(self, can_assign):
        #
        """
        """
        self.expression()
        self.consume(
            scanner.TokenType.TOKEN_RIGHT_PAREN,
            "Expect ')' after expression.",
        )

    def number(self, can_assign):
        #
        """
        """
        val = float(self.previous.source)
        self.emit_constant(value.number_val(val))

    def or_op(self, can_assign):
        #
        """
        """
        else_jump = self.emit_jump(chunk.OpCode.OP_JUMP_IF_FALSE)
        end_jump = self.emit_jump(chunk.OpCode.OP_JUMP)

        self.patch_jump(else_jump)
        self.emit_byte(chunk.OpCode.OP_POP)

        self.parse_precedence(Precedence.PREC_OR)
        self.patch_jump(end_jump)

    def string(self, can_assign):
        # type: () -> None
        """Extracts relevant section from string, wraps in a ObjectString, wraps
        in a Value and append to the stack."""
        # Start from position after quote
        chars = self.previous.source[1:self.previous.length - 1]

        # End from position before quote and end of string token
        val = value.copy_string(chars, self.previous.length - 2)

        self.emit_constant(value.obj_val(val))

    def named_variable(self, name, can_assign):
        #
        """
        """
        arg = self.resolve_local(name)

        if arg != -1:
            get_op = chunk.OpCode.OP_GET_LOCAL
            set_op = chunk.OpCode.OP_SET_LOCAL
        else:
            arg = self.identifier_constant(name)
            get_op = chunk.OpCode.OP_GET_GLOBAL
            set_op = chunk.OpCode.OP_SET_GLOBAL

        if can_assign and self.match(scanner.TokenType.TOKEN_EQUAL):
            self.expression()
            self.emit_bytes(set_op, arg)
        else:
            self.emit_bytes(get_op, arg)

    def variable(self, can_assign):
        # type: (bool) -> None
        """
        """
        self.named_variable(self.previous, can_assign)

    def unary(self, can_assign):
        #
        """
        """
        operator_type = self.previous.token_type

        # Compile the operand
        self.parse_precedence(Precedence.PREC_UNARY)

        # Emit the operator instruction
        if operator_type == scanner.TokenType.TOKEN_BANG:
            self.emit_byte(chunk.OpCode.OP_NOT)
        elif operator_type == scanner.TokenType.TOKEN_MINUS:
            self.emit_byte(chunk.OpCode.OP_NEGATE)

    def parse_precedence(self, precedence):
        #
        """
        """
        self.advance()
        prefix_rule = self.get_rule(self.previous.token_type).prefix

        if prefix_rule is None:
            self.error("Expect expression")
            return None

        can_assign = precedence.value <= Precedence.PREC_ASSIGNMENT.value
        prefix_rule(can_assign)

        while precedence.value <= self.get_rule(self.current.token_type).precedence.value:
            self.advance()

            infix_rule = self.get_rule(self.previous.token_type).infix
            infix_rule(can_assign)

        # Error if '=' not consumed as part of expression
        if can_assign and self.match(scanner.TokenType.TOKEN_EQUAL):
            self.error("Invalid assignment target.")

    def get_rule(self, token_type):
        # type: (TokenType) -> ParseRule
        """Custom function to convert TokenType to ParseRule. This allows the
        rule_map to consist of strings, which are then replaced by respective
        classes in the conversion process.
        """
        type_map = {
            "and_op": self.and_op,
            "binary": self.binary,
            "call": self.call,
            "grouping": self.grouping,
            "literal": self.literal,
            "number": self.number,
            "or_op": self.or_op,
            "string": self.string,
            "unary": self.unary,
            "variable": self.variable,
        }

        rule = rule_map[token_type.name]

        return ParseRule(
            prefix=type_map.get(rule[0], None),
            infix=type_map.get(rule[1], None),
            precedence=Precedence[rule[2]],
        )

    def expression(self):
        #
        """
        """
        self.parse_precedence(Precedence.PREC_ASSIGNMENT)

    def block(self):
        #
        """
        """
        while (not self.check(scanner.TokenType.TOKEN_RIGHT_BRACE)
               and not self.check(scanner.TokenType.TOKEN_EOF)):
            self.declaration()

        self.consume(scanner.TokenType.TOKEN_RIGHT_BRACE, "Expect '}' after block.")

    def function(self, function_type):
        #
        """
        """
        composer = Compiler(function_type, self.enclosing)

        if function_type != FunctionType.TYPE_SCRIPT:
            composer.function.name = value.copy_string(self.previous.source, self.previous.length)

        self.enclosing = composer
        self.begin_scope()

        # Compile the parameter list.
        self.consume(scanner.TokenType.TOKEN_LEFT_PAREN, "Expect '(' after function name.")

        if not self.check(scanner.TokenType.TOKEN_RIGHT_PAREN):
            while True:
                self.composer.function.arity += 1

                if self.composer.function.arity > 255:
                    self.error_at_current("Cannot have more than 255 parameters.")

                param_constant = self.parse_variable("Expect parameter name.")
                self.define_variable(param_constant)

                if not self.match(scanner.TokenType.TOKEN_COMMA):
                    break

        self.consume(scanner.TokenType.TOKEN_RIGHT_PAREN, "Expect ')' after function name.")

        # The body
        self.consume(scanner.TokenType.TOKEN_LEFT_BRACE, "Expect '{' before function body.")
        self.block()

        # Create the function object.
        function = self.end_compiler()
        self.emit_bytes(chunk.OpCode.OP_CONSTANT, self.make_constant(value.obj_val(function)))

    def fun_declaration(self):
        #
        """
        """
        global_fun = self.parse_variable("Expect function name.")

        self.mark_initialized()
        self.function(FunctionType.TYPE_FUNCTION)
        self.define_variable(global_fun)

    def var_declaration(self):
        #
        """
        """
        global_var = self.parse_variable("Expect variable name.")

        if self.match(scanner.TokenType.TOKEN_EQUAL):
            self.expression()
        else:
            self.emit_byte(chunk.OpCode.OP_NIL)

        self.consume(scanner.TokenType.TOKEN_SEMICOLON, "Expect ';' after variable declaration")

        self.define_variable(global_var)

    def expression_statement(self):
        #
        """
        """
        self.expression()
        self.consume(scanner.TokenType.TOKEN_SEMICOLON, "Expect ';' after expression.")
        self.emit_byte(chunk.OpCode.OP_POP)

    def for_statement(self):
        #
        """
        """
        self.begin_scope()

        self.consume(scanner.TokenType.TOKEN_LEFT_PAREN, "Expect '(' after 'for'")

        # Initializer clause. Allow either variable declaration or expression.
        if self.match(scanner.TokenType.TOKEN_SEMICOLON):
            pass
        elif self.match(scanner.TokenType.TOKEN_VAR):
            self.var_declaration()
        else:
            self.expression_statement()

        loop_start = self.current_chunk().count

        # Exit clause with condition expression
        exit_jump = -1

        if not self.match(scanner.TokenType.TOKEN_SEMICOLON):
            self.expression()
            self.consume(scanner.TokenType.TOKEN_SEMICOLON, "Expect ';' after loop condition.")

            # Jump out of loop if the condition is false
            exit_jump = self.emit_jump(chunk.OpCode.OP_JUMP_IF_FALSE)
            self.emit_byte(chunk.OpCode.OP_POP)

        # Increment clause
        if not self.match(scanner.TokenType.TOKEN_RIGHT_PAREN):
            body_jump = self.emit_jump(chunk.OpCode.OP_JUMP)
            increment_start = self.current_chunk().count

            self.expression()
            self.emit_byte(chunk.OpCode.OP_POP)
            self.consume(scanner.TokenType.TOKEN_RIGHT_PAREN, "Expect ')' after for clauses")

            self.emit_loop(loop_start)
            loop_start = increment_start
            self.patch_jump(body_jump)

        self.statement()
        self.emit_loop(loop_start)

        if exit_jump != -1:
            self.patch_jump(exit_jump)
            self.emit_byte(chunk.OpCode.OP_POP)

        self.end_scope()

    def if_statement(self):
        #
        """
        """
        self.consume(scanner.TokenType.TOKEN_LEFT_PAREN, "Expect '(' after 'if'")
        self.expression()
        self.consume(scanner.TokenType.TOKEN_RIGHT_PAREN, "Expect ')' after 'if'")

        then_jump = self.emit_jump(chunk.OpCode.OP_JUMP_IF_FALSE)
        self.emit_byte(chunk.OpCode.OP_POP)
        self.statement()

        else_jump = self.emit_jump(chunk.OpCode.OP_JUMP)

        self.patch_jump(then_jump)
        self.emit_byte(chunk.OpCode.OP_POP)

        if self.match(scanner.TokenType.TOKEN_ELSE):
            self.statement()

        self.patch_jump(else_jump)

    def print_statement(self):
        #
        """
        """
        self.expression()
        self.consume(scanner.TokenType.TOKEN_SEMICOLON, "Expect ';' after value.")
        self.emit_byte(chunk.OpCode.OP_PRINT)

    def return_statement(self):
        #
        """
        """
        if self.enclosing.function_type == FunctionType.TYPE_SCRIPT:
            self.error("Cannot return from top-level code.")

        if self.match(scanner.TokenType.TOKEN_SEMICOLON):
            self.emit_return()
        else:
            self.expression()
            self.consume(scanner.TokenType.TOKEN_SEMICOLON, "Expect ';' after return value.")
            self.emit_byte(chunk.OpCode.OP_RETURN)

    def while_statement(self):
        #
        """
        """
        loop_start = self.current_chunk().count

        self.consume(scanner.TokenType.TOKEN_LEFT_PAREN, "Expect '(' after 'if'")
        self.expression()
        self.consume(scanner.TokenType.TOKEN_RIGHT_PAREN, "Expect ')' after 'if'")

        exit_jump = self.emit_jump(chunk.OpCode.OP_JUMP_IF_FALSE)

        self.emit_byte(chunk.OpCode.OP_POP)
        self.statement()

        self.emit_loop(loop_start)

        self.patch_jump(exit_jump)
        self.emit_byte(chunk.OpCode.OP_POP)

    def synchronize(self):
        #
        """
        """
        self.panic_mode = False

        while self.current.token_type != scanner.TokenType.TOKEN_EOF:
            if self.previous.token_type == scanner.TokenType.TOKEN_SEMICOLON:
                return None

            if self.current.token_type == scanner.TokenType.TOKEN_RETURN:
                return None

            self.advance()

    def declaration(self):
        #
        """
        """
        if self.match(scanner.TokenType.TOKEN_FUN):
            self.fun_declaration()
        elif self.match(scanner.TokenType.TOKEN_VAR):
            self.var_declaration()
        else:
            self.statement()

        if self.panic_mode:
            self.synchronize()

    def statement(self):
        #
        """
        """
        if self.match(scanner.TokenType.TOKEN_PRINT):
            self.print_statement()
        elif self.match(scanner.TokenType.TOKEN_FOR):
            self.for_statement()
        elif self.match(scanner.TokenType.TOKEN_IF):
            self.if_statement()
        elif self.match(scanner.TokenType.TOKEN_RETURN):
            self.return_statement()
        elif self.match(scanner.TokenType.TOKEN_WHILE):
            self.while_statement()
        elif self.match(scanner.TokenType.TOKEN_LEFT_BRACE):
            self.begin_scope()
            self.block()
            self.end_scope()
        else:
            self.expression_statement()


def compile(source, bytecode, debug_level):
    # type: (str, chunk.Chunk, bool) -> value.ObjectFunction
    """KIV change this to Compiler class with method compile."""
    reader = scanner.Scanner(source)
    composer = Compiler(FunctionType.TYPE_SCRIPT, None)

    parser = Parser(
        reader=reader,
        composer=composer,
        bytecode=bytecode,
        debug_level=debug_level,
    )

    if parser.debug_level >= 2:
        print("\n== tokens ==")

    parser.advance()

    while not parser.match(scanner.TokenType.TOKEN_EOF):
        parser.declaration()

    function = parser.end_compiler()

    if parser.had_error:
        return None

    return function
