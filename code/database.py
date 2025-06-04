import os
import struct
from struct import Struct

TABLE_META_SIZE = 4358
MAX_TABLE_COUNT = 255
MAX_COLUMN_COUNT = 255
PAGE_SIZE = 4096
DATA_TYPES = {'integer': 0, 'float': 1, 'string': 2}
STRUCT_TYPES = {0: 'i', 1: 'f', 2: '255s'}
CHECK_TYPES = {0: int, 1: float, 2: str}
DEAD_END = 256**4 - 1

def decode_string(string: bytes):
    return string[:string.index(b'\x00')].decode('utf-8')

class Database:
    def __init__(self, path):
        self.filepath = path
        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w+b') as file:
                file.write(b'\x00' * (TABLE_META_SIZE * MAX_TABLE_COUNT + 3) + b'\xff\xff\xff\xff' + b'\x00' * (PAGE_SIZE - 4))                

    def _allocate_page(self):
        with open(self.filepath, 'r+b') as file:
            file.seek(1)
            vacant_page = struct.unpack('=H', file.read(2))[0]
            file.seek(1)
            file.write(struct.pack('=H', vacant_page + 1))
            file.seek(0, 2)
            file.write(b'\xff\xff\xff\xff' + b'\x00' * (PAGE_SIZE - 4))    

    def create_table(self, table_name: str, columns: dict[str, str]):
        if len(table_name) > 16:
            raise ValueError('Имя таблицы длиннее 16 символов')                
        with open(self.filepath, 'r+b') as file:            
            table_count, vacant_page = struct.unpack('=BH', file.read(3))
            if table_count < MAX_TABLE_COUNT:
                file.seek(0)
                file.write(struct.pack('=B', table_count + 1))
            else: 
                raise ValueError(f'Достигнуто максимальное число таблиц ({MAX_TABLE_COUNT})')
            if len(columns) > MAX_COLUMN_COUNT:
                raise ValueError(f'Максимальное количество столбцов: {MAX_COLUMN_COUNT}')
            for v in columns.values():
                if v not in DATA_TYPES:
                    raise TypeError(f'Unknown type {v}')
            table_meta_offset = 3 + table_count * TABLE_META_SIZE
            rec_size = struct.calcsize('=' + ''.join(STRUCT_TYPES[DATA_TYPES[v]] for v in columns.values()))
            table_meta = struct.pack('=16sHHHB', table_name.encode('utf-8'), vacant_page, vacant_page, rec_size, len(columns))            
            for col, data_type in columns.items():
                if len(col) > 16:
                    raise ValueError(f'Название столбца "{col}" длиннее 16 символов')
                if data_type not in DATA_TYPES:
                    raise TypeError(f'Unknown type: {data_type}')
                table_meta += struct.pack('=16sB', col.encode('utf-8'), DATA_TYPES[data_type])
            table_meta = table_meta.ljust(TABLE_META_SIZE, b'\x00')
            file.seek(table_meta_offset)
            file.write(table_meta)
            file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + vacant_page * PAGE_SIZE)
            next_page = struct.unpack('=I', file.read(4))[0]
            if next_page == DEAD_END:
                self._allocate_page()
            else:
                file.seek(-4, 1)
                file.write(b'\xff\xff\xff\xff')
                file.seek(1)
                file.write(struct.pack('=H', next_page))

    def insert(self, table_name: str, values: list):        
        with open(self.filepath, 'r+b') as file:
            table_count, vacant_page = struct.unpack('=BH', file.read(3))
            found = False
            for i in range(table_count):
                file.seek(3 + i * TABLE_META_SIZE)
                table_meta_pos = file.tell()
                name, _, last_page, rec_size, col_count = struct.unpack('=16sHHHB', file.read(23))
                found = decode_string(name) == table_name
                if found:
                    break
            if not found:
                raise NameError('Таблица не существует')
            types = [struct.unpack('=16sB', file.read(17))[1] for _ in range(col_count)]
            if len(values) != col_count:
                raise ValueError(f'Insufficient number of values, should be {col_count}')
            for i in range(col_count):
                if not isinstance(values[i], CHECK_TYPES[types[i]]):
                    raise TypeError(f'Wrong type: {type(values[i])}, expected {CHECK_TYPES[types[i]]}')
                if isinstance(values[i], str):
                    values[i] = values[i].encode('utf-8')
            rec_packer = Struct('=' + ''.join(STRUCT_TYPES[t] for t in types))
            file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + last_page * PAGE_SIZE)
            _, rec_count = struct.unpack('=IH', file.read(6))
            if 6 + rec_size * rec_count + rec_size <= PAGE_SIZE:
                file.seek(-2, 1)
                file.write(struct.pack('=H', rec_count + 1))
                file.seek(rec_size * rec_count, 1)
                file.write(rec_packer.pack(*values))
            else:
                file.seek(-6, 1)
                file.write(struct.pack('=I', vacant_page))
                file.seek(table_meta_pos + 18)
                file.write(struct.pack('=H', vacant_page))
                file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + vacant_page * PAGE_SIZE)
                next_page = struct.unpack('=I', file.read(4))[0]
                file.seek(-4, 1)
                file.write(b'\xff\xff\xff\xff\x01\x00')
                file.write(rec_packer.pack(*values))
                if next_page == DEAD_END:
                    self._allocate_page()
                else:
                    file.seek(1)
                    file.write(struct.pack('=H', next_page))

    def select(self, table_name: str, columns: list, where=lambda row: True) -> tuple[dict, dict]:
        with open(self.filepath, 'rb') as file:
            table_count, _ = struct.unpack('=BH', file.read(3))
            found = False
            for i in range(table_count):
                file.seek(3 + i * TABLE_META_SIZE)
                name, first_page, _, rec_size, col_count = struct.unpack('=16sHHHB', file.read(23))
                found = decode_string(name) == table_name
                if found:
                    break
            if not found:
                raise NameError('Таблица не существует')            
            table_columns = []
            types = []
            records = []
            for _ in range(col_count):
                col, type = struct.unpack('=16sB', file.read(17))
                table_columns.append(decode_string(col))
                types.append(type)
            rec_unpack = Struct('=' + ''.join(STRUCT_TYPES[t] for t in types))
            next_page = first_page
            while next_page != DEAD_END:
                file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + next_page * PAGE_SIZE)
                next_page, rec_count = struct.unpack('=IH', file.read(6))
                if rec_count != 0:
                    records.extend([decode_string(r) if isinstance(r, bytes) else r for r in rec_unpack.unpack(file.read(rec_size))] for _ in range(rec_count))
                else:
                    break
        selected_columns = table_columns if '*' in columns else columns
        data = [dict(zip(table_columns, rec)) for rec in records]
        res_data = [{col: d[col] for col in selected_columns} for d in data if where(d)]
        res_column = dict(zip(table_columns, types))
        return {col: res_column[col] for col in selected_columns}, res_data
    
    def update(self, table_name: str, updated_values: dict, where=lambda row: True):
        with open(self.filepath, 'r+b') as file:
            table_count, _ = struct.unpack('=BH', file.read(3))
            found = False
            for i in range(table_count):
                file.seek(3 + i * TABLE_META_SIZE)
                name, first_page, _, rec_size, col_count = struct.unpack('=16sHHHB', file.read(23))
                found = decode_string(name) == table_name
                if found:
                    break
            if not found:
                raise NameError('Таблица не существует')
            table_columns = []
            types = []            
            for _ in range(col_count):
                col, t = struct.unpack('=16sB', file.read(17))
                table_columns.append(decode_string(col))
                types.append(t)
            table_col_types = dict(zip(table_columns, types))
            for c in updated_values:
                if c not in table_columns:
                    raise NameError(f'Column {c} does not exist')
                if not isinstance(updated_values[c], CHECK_TYPES[table_col_types[c]]):
                    raise TypeError(f'Wrong type: {type(updated_values[c])}, expected: {CHECK_TYPES[table_col_types[c]]}')            
            rec_packer = Struct('=' + ''.join(STRUCT_TYPES[t] for t in types))
            next_page = first_page
            while next_page != DEAD_END:
                file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + next_page * PAGE_SIZE)
                next_page, rec_count = struct.unpack('=IH', file.read(6))
                for _ in range(rec_count):
                    rec = [decode_string(r) if isinstance(r, bytes) else r for r in rec_packer.unpack(file.read(rec_size))]
                    data = dict(zip(table_columns, rec))
                    if where(data):
                        data.update(updated_values)
                        updated_rec = [v.encode('utf-8') if isinstance(v, str) else v for v in data.values()]
                        file.seek(-rec_size, 1)
                        file.write(rec_packer.pack(*updated_rec))

    def delete(self, table_name: str, where=lambda row: True):
        with open(self.filepath, 'r+b') as file:
            table_count, vacant_page = struct.unpack('=BH', file.read(3))
            found = False
            for i in range(table_count):
                file.seek(3 + i * TABLE_META_SIZE)
                table_meta_pos = file.tell()
                name, first_page, last_page, rec_size, _ = struct.unpack('=16sHHHB', file.read(23))
                found = decode_string(name) == table_name
                if found:
                    break
            if not found:
                raise NameError('Таблица не существует')
            table_columns, data = self.select(table_name, '*')
            rec_packer = Struct('=' + ''.join(STRUCT_TYPES[v] for v in table_columns.values()))
            changed_data = [rec_packer.pack(*[v.encode('utf-8') if isinstance(v, str) else v for v in rec.values()]) for rec in data if not where(rec)]
            next_page = first_page
            old_last_page = last_page
            old_vacant_page = vacant_page
            transfered = False
            while next_page != DEAD_END:
                if not transfered:
                    last_page = next_page
                file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + next_page * PAGE_SIZE)
                start_pos = file.tell()
                next_page, _ = struct.unpack('=IH', file.read(6))
                if not transfered:
                    if next_page != DEAD_END: vacant_page = next_page
                pack = b''
                rec_count = 0
                while len(changed_data) > 0 and 6 + rec_size * rec_count + rec_size <= PAGE_SIZE:
                    pack += changed_data.pop(0)
                    rec_count += 1
                transfered = len(changed_data) == 0                    
                pack = pack.ljust(PAGE_SIZE - 6, b'\x00')
                file.write(pack)
                file.seek(start_pos + 4)
                file.write(struct.pack('=H', rec_count))
            if old_last_page != last_page:
                file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + old_last_page * PAGE_SIZE)
                file.write(struct.pack('=I', old_vacant_page))
            file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + last_page * PAGE_SIZE)
            file.write(b'\xff\xff\xff\xff')
            file.seek(1)
            file.write(struct.pack('=H', vacant_page))
            file.seek(table_meta_pos + 18)
            file.write(struct.pack('=H', last_page))

    def drop_table(self, table_name):
        self.delete(table_name)
        with open(self.filepath, 'r+b') as file:
            table_count, vacant_page = struct.unpack('=BH', file.read(3))
            found = False
            for i in range(table_count):
                file.seek(3 + i * TABLE_META_SIZE)
                table_meta_pos = file.tell()
                name, first_page, last_page, rec_size, _ = struct.unpack('=16sHHHB', file.read(23))
                found = decode_string(name) == table_name
                if found:
                    break
            if not found:
                raise NameError('Таблица не существует')            
            file.seek(3 + TABLE_META_SIZE * MAX_TABLE_COUNT + first_page * PAGE_SIZE)
            file.write(struct.pack('=I', vacant_page))
            file.seek(0)
            file.write(struct.pack('=BH', table_count - 1, first_page))
            file.seek(table_meta_pos + TABLE_META_SIZE)
            remaining = file.read(TABLE_META_SIZE * (table_count - i))
            erase_pos = file.tell()
            file.seek(table_meta_pos)
            file.write(remaining)
            file.seek(erase_pos)
            file.write(b'\x00' * TABLE_META_SIZE)
            