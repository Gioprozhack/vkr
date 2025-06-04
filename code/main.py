import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.filedialog as filedialog
from parser import parse_command
from database import Database

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry('600x400')   
        self.title('СУБД')

        self.selected_db = None
            
        self.main_menu = tk.Menu()
        self.file_menu = tk.Menu(tearoff=0)
        
        self.main_menu.add_command(label='Выбрать БД', command=self.select_database)
             
        self.main_menu.add_command(label='Запуск', command=self.execute_sql)              
        self.config(menu=self.main_menu)

        self.table_frame = tk.Frame(self)        
        self.table = ttk.Treeview(master=self.table_frame)
        self.table.pack(fill='both', expand=1)

        self.ysb = ttk.Scrollbar(self.table, orient=tk.VERTICAL, command=self.table.yview)
        self.xsb = ttk.Scrollbar(self.table, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(xscrollcommand=self.xsb.set, yscrollcommand=self.ysb.set)
        self.ysb.pack(side='right', fill='y')
        self.xsb.pack(side='bottom', fill='x')

        self.sql_field_frame = tk.Frame(self)        
        self.sql_field = tk.Text(master=self.sql_field_frame)
        self.sql_field.pack(fill='both', expand=1)         

        self.table_frame.place(x=5, y=10, relheight=0.5, relwidth=1.0, width=self.winfo_width() - 5)
        self.sql_field_frame.place(x=5, y=10, rely=0.5, relheight=0.5, relwidth=1.0)  

    def update_table(self, headings, contents):
        self.table.delete(*self.table.get_children())
        self.table['columns'] = [h for h in headings]
        self.table['show'] = 'headings'     
        for h in headings:
            self.table.heading(h, text=h)
            self.table.column(h, width=100, anchor="center")
        for c in contents:
            self.table.insert("", tk.END, values=list(c.values())) 
    
    def select_database(self):
        file_path = filedialog.askopenfilename(defaultextension=".db", filetypes=[("Database files", "*.db")], initialdir='databases/')
        if file_path:            
            self.selected_db = Database(file_path)

    def execute_sql(self):
        try:
            parsed = parse_command(self.sql_field.get('1.0', 'end'), self.selected_db)
            if isinstance(parsed, Database):                
                self.selected_db = parsed
            elif isinstance(parsed, tuple):
                self.update_table(*parsed)
        except Exception as e:
            messagebox.showerror('Error', str(e))

window = MainWindow()
window.mainloop()