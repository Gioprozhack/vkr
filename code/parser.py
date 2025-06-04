import ast
from database import Database

class CommandError(Exception):
    pass

def eval_node(node: ast.Expression, row: dict = None):

    if isinstance(node, ast.Expression):
        return eval_node(node.body, row)
    
    elif isinstance(node, ast.Name):
        return row[node.id]
    
    elif isinstance(node, ast.Constant):
        return node.value
    
    elif isinstance(node, ast.Dict):        
        keys = node.keys
        values = node.values
        return {eval_node(keys[i], row): eval_node(values[i], row) for i in range(len(keys))}        
    
    elif isinstance(node, ast.BinOp):
        op = node.op
        left = eval_node(node.left, row)
        right = eval_node(node.right, row)
        if isinstance(op, ast.Add): return left + right
        if isinstance(op, ast.Sub): return left - right
        if isinstance(op, ast.Mult): return left * right
        if isinstance(op, ast.Div): return left / right
        if isinstance(op, ast.FloorDiv): return left // right
        if isinstance(op, ast.Mod): return left % right    
        if isinstance(op, ast.Pow): return left ** right    

    elif isinstance(node, ast.Compare):
        op = node.ops[0]
        left = eval_node(node.left, row)
        right = eval_node(node.comparators[0], row)
        if isinstance(op, ast.Gt): return left > right
        if isinstance(op, ast.GtE): return left >= right
        if isinstance(op, ast.Lt): return left < right
        if isinstance(op, ast.LtE): return left <= right
        if isinstance(op, ast.Eq): return left == right
        if isinstance(op, ast.NotEq): return left != right

    elif isinstance(node, ast.BoolOp):
        op = node.op
        if isinstance(op, ast.And):
            return all(eval_node(value, row) for value in node.values)
        
        if isinstance(op, ast.Or):
            return any(eval_node(value, row) for value in node.values)
        
    elif isinstance(node, ast.UnaryOp):
        op = node.op
        if isinstance(op, ast.USub): return -eval_node(node.operand, row)
        if isinstance(op, ast.Not): return not(eval_node(node.operand, row))

    else:
        raise ValueError(f"Unsupported AST node type: {type(node).__name__}")    
    

def parse_command(command: str, db: Database):
    command = command.strip()
    if not command:
        raise CommandError("Пустая команда")

    tokens = command.split()
    action = tokens[0].lower() if tokens else ""

    try:
        if action == 'create':
            if len(tokens) < 2:
                raise CommandError(
                    "Ожидаемый синтаксис:\n"
                    "create table <имя_таблицы> <столбец1> <тип1> [<столбец2> <тип2> ...]\n"
                    "или\n"
                    "create database <имя_бд>"
                )

            if tokens[1] == 'table':
                if len(tokens) < 4 or len(tokens) % 2 == 0:
                    raise CommandError(
                        "Ожидаемый синтаксис для создания таблицы:\n"
                        "create table <имя_таблицы> <столбец1> <тип1> [<столбец2> <тип2> ...]\n"                        
                    )
                
                table_name = tokens[2]
                columns = tokens[3::2]
                types = tokens[4::2]
                
                if len(columns) != len(types):
                    raise CommandError(
                        "Несоответствие количества столбцов и типов\n"
                        "Ожидаемый синтаксис: create table <имя> <столбец1> <тип1> <столбец2> <тип2> ..."
                    )
                
                db.create_table(table_name, dict(zip(columns, types)))
                return db.select(table_name, ['*'])

            elif tokens[1] == 'database':
                if len(tokens) != 3:
                    raise CommandError(
                        "Ожидаемый синтаксис для создания БД:\n"
                        "create database <имя_бд>\n"                        
                    )
                db_name = tokens[2]
                path = f'databases/{db_name}.db'
                return Database(path)

            else:
                raise CommandError(
                    "Неизвестная create команда\n"
                    "Допустимые варианты:\n"
                    "create table <имя> <столбцы...>\n"
                    "create database <имя>"
                )

        elif action == 'insert':
            if len(tokens) < 5 or tokens[1] != 'into' or tokens[3] != 'values':
                raise CommandError(
                    "Ожидаемый синтаксис:\n"
                    "insert into <таблица> values <значение1> <значение2> ..."                    
                )
            
            table_name = tokens[2]
            values = []
            for value in tokens[4:]:
                try:
                    parsed_value = eval_node(ast.parse(value, mode='eval'))
                    values.append(parsed_value)
                except:
                    raise CommandError(
                        f"Некорректное значение: {value}\n"                        
                    )
            
            db.insert(table_name, values)
            return db.select(table_name, ['*'])

        elif action == 'select':
            if len(tokens) < 4 or 'from' not in tokens:
                raise CommandError(
                    "Ожидаемый синтаксис:\n"
                    "select <столбцы|*> from <таблица> [where <условие>]"                    
                )
            
            try:
                from_index = tokens.index('from')
                columns = tokens[1:from_index]
                table_name = tokens[from_index + 1]
            except:
                raise CommandError(
                    "Некорректный синтаксис после select\n"
                    "Ожидаемый формат: select <столбцы> from <таблица>"
                )

            where_clause = 'True'
            if 'where' in tokens:
                where_index = tokens.index('where')
                if where_index == len(tokens) - 1:
                    raise CommandError(
                        "Отсутствует условие после where"                        
                    )
                where_clause = ' '.join(tokens[where_index + 1:])
            
            try:
                where_node = ast.parse(where_clause, mode='eval')
            except SyntaxError:
                raise CommandError(
                    f"Некорректное условие WHERE: {where_clause}"                    
                )
            
            return db.select(table_name, columns, where=lambda row: eval_node(where_node, row))

        elif action == 'delete':
            if len(tokens) < 3 or tokens[1] != 'from':
                raise CommandError(
                    "Ожидаемый синтаксис:\n"
                    "delete from <таблица> [where <условие>]"                    
                )
            
            table_name = tokens[2]
            
            where_clause = 'True'
            if 'where' in tokens:
                where_index = tokens.index('where')
                if where_index == len(tokens) - 1:
                    raise CommandError(
                        "Отсутствует условие после where"                        
                    )
                where_clause = ' '.join(tokens[where_index + 1:])
            
            try:
                where_node = ast.parse(where_clause, mode='eval')
            except SyntaxError:
                raise CommandError(
                    f"Некорректное условие WHERE: {where_clause}"                    
                )
            
            db.delete(table_name, where=lambda row: eval_node(where_node, row))
            return db.select(table_name, ['*'])

        elif action == 'update':
            if len(tokens) < 5 or tokens[2] != 'set':
                raise CommandError(
                    "Ожидаемый синтаксис:\n"
                    "update <таблица> set <столбец1> <значение1> [<столбец2> <значение2> ...] [where <условие>]"                    
                )
            
            table_name = tokens[1]
            where_index = tokens.index('where') if 'where' in tokens else len(tokens)
            
            if (where_index - 3) % 2 != 0:
                raise CommandError(
                    "Нечетное количество аргументов в SET\n"
                    "Ожидается пары: <столбец> <значение>"                    
                )
            
            try:
                updates = {}
                i = 3
                while i < where_index:
                    col = tokens[i]
                    val = eval_node(ast.parse(tokens[i+1], mode='eval'))
                    updates[col] = val
                    i += 2
            except Exception as e:
                raise CommandError(
                    f"Ошибка в аргументах SET: {str(e)}\n"
                    "Ожидается: update <таблица> set <столбец1> <значение1> [<столбец2> <значение2>...]"                    
                )
            
            where_clause = 'True'
            if 'where' in tokens:
                if where_index == len(tokens) - 1:
                    raise CommandError(
                        "Отсутствует условие после where"                        
                    )
                where_clause = ' '.join(tokens[where_index + 1:])
            
            try:
                where_node = ast.parse(where_clause, mode='eval')
            except SyntaxError:
                raise CommandError(
                    f"Некорректное условие WHERE: {where_clause}"                    
                )
            
            db.update(table_name, updates, where=lambda row: eval_node(where_node, row))
            return db.select(table_name, ['*'])
        
        elif action == 'drop':
            if len(tokens) != 3 or tokens[1] != 'table':
                raise CommandError(
                    "Ожидаемый синтаксис:\n"
                    "drop table <имя_таблицы>"                    
                )
            
            table_name = tokens[2]
            db.drop_table(table_name)
            return [], [{}]
        
        else:
            raise CommandError(
                f"Неизвестная команда: {action}\n"
                "Доступные команды:\n"
                "create table/database ...\n"
                "drop table ...\n"
                "insert into ...\n"
                "select ... from ...\n"
                "update ... set ...\n"
                "delete from ..."
            )

    except Exception:
        raise
    except Exception as e:
        raise CommandError(f"Ошибка выполнения команды: {str(e)}")