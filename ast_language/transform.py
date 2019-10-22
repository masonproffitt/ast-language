from .linq_util import Select

import lark

import ast
import sys


UnaryOp_ops = {'not': ast.Not}

BinOp_ops = {'+': ast.Add,
             '-': ast.Sub,
             '*': ast.Mult,
             '/': ast.Div}

BoolOp_ops = {'and': ast.And,
              'or':  ast.Or}

Compare_ops = {'==': ast.Eq,
               '!=': ast.NotEq,
               '<':  ast.Lt,
               '<=': ast.LtE,
               '>':  ast.Gt,
               '>=': ast.GtE}

op_strings = {value: key for dictionary in [UnaryOp_ops, BinOp_ops, BoolOp_ops, Compare_ops]
                         for key, value in dictionary.items()}

class PythonASTToTextASTTransformer(ast.NodeVisitor):
    def visit_Module(self, node):
        n_children = len(node.body)
        if n_children == 0:
            return ''
        elif n_children == 1:
            return self.visit(node.body[0])
        else:
            raise SyntaxError('A record must contain zero or one expressions; found '
                              + str(n_children))

    def visit_Expr(self, node):
        return self.visit(node.value)

    def visit_Name(self, node):
        return node.id

    def visit_Num(self, node):
        return repr(node.n)

    def visit_Str(self, node):
        return repr(node.s)

    def visit_NameConstant(self, node):
        return repr(node.value)

    @staticmethod
    def make_composite_node_string(node_type, *fields):
        return '(' + node_type + ''.join([' ' + field for field in fields]) + ')'

    def visit_List(self, node):
        return self.make_composite_node_string('list',
                                               *[self.visit(element) for element in node.elts])

    def visit_Tuple(self, node):
        return self.visit_List(node)

    def visit_Attribute(self, node):
        return self.make_composite_node_string('attr', self.visit(node.value), repr(node.attr))

    def visit_Call(self, node):
        return self.make_composite_node_string('call',
                                               self.visit(node.func),
                                               *[self.visit(arg) for arg in node.args])

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.UAdd):
            return self.visit(node.operand)
        elif isinstance(node.op, ast.USub):
            if isinstance(node.operand, ast.Num):
                return self.visit(ast.Num(n=-node.operand.n))
            else:
                raise SyntaxError('Unsupported unary - operand type: ' + type(node.operand))
        else:
            return self.make_composite_node_string(op_strings[type(node.op)],
                                                   self.visit(node.operand))

    def visit_BinOp(self, node):
        return self.make_composite_node_string(op_strings[type(node.op)],
                                               self.visit(node.left),
                                               self.visit(node.right))

    def visit_BoolOp(self, node):
        if len(node.values) < 2:
            raise SyntaxError('Boolean operator must have at least 2 operands; found: '
                              + len(node.values))
        rep = self.visit(node.values[0])
        for value in node.values[1:]:
            rep = self.make_composite_node_string(op_strings[type(node.op)],
                                                  rep,
                                                  self.visit(value))
        return rep

    def visit_Compare(self, node):
        rep = self.visit(node.left)
        for operator, comparator in zip(node.ops, node.comparators):
            rep = self.make_composite_node_string(op_strings[type(operator)],
                                                  rep,
                                                  self.visit(comparator))
        return rep

    def visit_Lambda(self, node):
        return self.make_composite_node_string('lambda',
                                               self.visit(node.args),
                                               self.visit(node.body))

    def visit_arguments(self, node):
        return self.visit(ast.List(elts=node.args))

    def visit_arg(self, node):
        return node.arg

    def visit_Select(self, node):
        return self.make_composite_node_string('Select',
                                               self.visit(node.source),
                                               self.visit(node.selector))

    def generic_visit(self, node):
        raise SyntaxError('Unsupported node type: ' + str(type(node)))


class TextASTToPythonASTTransformer(lark.Transformer):
    def record(self, children):
        if (len(children) == 0
           or isinstance(children[0], lark.Token) and children[0].type == 'WHITESPACE'):
            return ast.Module(body=[])
        return ast.Module(body=[ast.Expr(value=children[0])])

    def expression(self, children):
        for child in children:
            if not (isinstance(child, lark.Token) and child.type == 'WHITESPACE'):
                return child
        raise SyntaxError('Expression does not contain a node')

    def atom(self, children):
        child = children[0]
        if child.type == 'IDENTIFIER':
            if child.value in ['True', 'False', 'None']:
                return ast.NameConstant(value=ast.literal_eval(child.value))
            return ast.Name(id=child.value, ctx=ast.Load())
        elif child.type == 'STRING_LITERAL':
            return ast.Str(s=ast.literal_eval(child.value))
        elif child.type == 'NUMERIC_LITERAL':
            if child.value[0] == '+':
                child.value = child.value[1:]
            number = ast.literal_eval(child.value)
            if number < 0 and sys.version_info[0] > 2:
                return ast.UnaryOp(op=ast.USub(), operand=ast.Num(n=-number))
            else:
                return ast.Num(n=number)
        else:
            raise Exception('Unknown atom child type: ' + str(child.type))

    def composite(self, children):
        fields = []
        for child in children:
            if isinstance(child, lark.Token):
                if child.type == 'NODE_TYPE':
                    node_type = child.value
                else:
                    pass
            elif isinstance(child, ast.AST):
                fields.append(child)
            else:
                pass

        if node_type == 'list':
            return ast.List(elts=fields, ctx=ast.Load())

        elif node_type == 'attr':
            if len(fields) != 2:
                raise SyntaxError('Attribute node must have two fields; found ' + len(fields))
            if not isinstance(fields[1], ast.Str):
                raise SyntaxError('Attribute name must be a string; found ' + type(fields[1]))
            return ast.Attribute(value=fields[0], attr=fields[1].s, ctx=ast.Load())

        elif node_type == 'call':
            if len(fields) < 1:
                raise SyntaxError('Call node must have at least one field; found ' + len(fields))
            if sys.version_info[0] < 3:
                return ast.Call(func=fields[0],
                                args=fields[1:],
                                keywords=[],
                                starargs=None,
                                kwargs=None)
            else:
                return ast.Call(func=fields[0], args=fields[1:], keywords=[])

        elif node_type in UnaryOp_ops:
            if len(fields) == 1:
                return ast.UnaryOp(op=UnaryOp_ops[node_type](), operand=fields[0])
            else:
                raise SyntaxError(UnaryOp_ops[node_type]
                                  + ' operator only supported for one operand; found '
                                  + len(fields))

        elif node_type in BinOp_ops:
            if len(fields) == 2:
                return ast.BinOp(left=fields[0], op=BinOp_ops[node_type](), right=fields[1])
            else:
                raise SyntaxError(BinOp_ops[node_type]
                                  + ' operator only supported for two operands; found '
                                  + len(fields))

        elif node_type in BoolOp_ops:
            if len(fields) == 2:
                return ast.BoolOp(op=BoolOp_ops[node_type](), values=fields)
            else:
                raise SyntaxError(BoolOp_ops[node_type]
                                  + ' operator only supported for two operands; found '
                                  + len(fields))

        elif node_type in Compare_ops:
            if len(fields) == 2:
                return ast.Compare(left=fields[0], ops=[Compare_ops[node_type]()], comparators=[fields[1]])
            else:
                raise SyntaxError(Compare_ops[node_type]
                                  + ' operator only supported for two operands; found '
                                  + len(fields))

        elif node_type == 'lambda':
            if len(fields) != 2:
                raise SyntaxError('Lambda node must have two fields; found ' + len(fields))
            if not isinstance(fields[0], ast.List):
                raise SyntaxError('Lambda arguments must be in a list; found ' + type(fields[0]))
            for arg in fields[0].elts:
                if not isinstance(arg, ast.Name):
                    raise SyntaxError('Lambda arguments must variable names; found ' + type(arg))
            if sys.version_info[0] < 3:
                return ast.Lambda(args=ast.arguments(args=[ast.Name(id=name.id, ctx=ast.Param())
                                                           for name in fields[0].elts],
                                                     vararg=None,
                                                     kwarg=None,
                                                     defaults=[]),
                                  body=fields[1])
            else:
                return ast.Lambda(args=ast.arguments(args=[ast.arg(arg=name.id, annotation=None)
                                                           for name in fields[0].elts],
                                                     vararg=None,
                                                     kwonlyargs=[],
                                                     kw_defaults=[],
                                                     kwarg=None,
                                                     defaults=[]),
                                  body=fields[1])

        elif node_type == 'Select':
            if len(fields) != 2:
                raise SyntaxError('Select node must have two fields; found ' + len(fields))
            if not isinstance(fields[1], ast.Lambda):
                raise SyntaxError('Select selector must be a lambda; found ' + type(fields[1]))
            if len(fields[1].args.args) != 1:
                raise SyntaxError('Select selector must have exactly one argument; found '
                                  + len(fields[1].args.args))
            return Select(source=fields[0], selector=fields[1])

        else:
            raise SyntaxError('Unknown composite node type: ' + node_type)
