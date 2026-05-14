import pandas as pd
import pyodbc
import numpy as np
import sqlalchemy
from .db_fetcher_Airflow import SQL_Query



# DB Schema

# CREATE TABLE [dbo].[InvoiceFile](
#     [InvoiceFileId] INT IDENTITY(1,1) NOT NULL,     
#     [FileName] NVARCHAR (260),  
#     [FilePath] NVARCHAR (260),  
#     [InvoiceFileStatusId] INT,  
#     [FTPDroppedDate] DATETIME,  
#     [LastModifiedDate] DATETIME,    
#     [Created] DATETIME CONSTRAINT [DF_InvoiceFile_Created] DEFAULT GETDATE() NULL,
#     [CreatedBy] VARCHAR(50) CONSTRAINT [DF_InvoiceFile_CreatedBy] DEFAULT SUSER_NAME() NULL,
#     [LastUpd] DATETIME CONSTRAINT [DF_InvoiceFile_LastUpd] DEFAULT GETDATE() NULL,
#     [LastUpdBy] VARCHAR(50) CONSTRAINT [DF_InvoiceFile_LastUpdBy] DEFAULT SUSER_NAME() NULL,
#     [LastUpdApp] VARCHAR(250) CONSTRAINT [DF_InvoiceFile_LastUpdApp] DEFAULT APP_NAME() NULL,
#     CONSTRAINT PK_InvoiceFile_InvoiceFileId PRIMARY KEY CLUSTERED (InvoiceFileId)
# ) ON [PRIMARY]
# GO

# CREATE TABLE [dbo].[InvoiceFileStatus](
#     [InvoiceFileStatusId] INT NOT NULL, 
#     [Description] VARCHAR(200) NOT NULL,    
#     [Created] DATETIME CONSTRAINT [DF_InvoiceFileStatus_Created] DEFAULT GETDATE() NULL,
#     [CreatedBy] VARCHAR(50) CONSTRAINT [DF_InvoiceFileStatus_CreatedBy] DEFAULT SUSER_NAME() NULL,
#     [LastUpd] DATETIME CONSTRAINT [DF_InvoiceFileStatus_LastUpd] DEFAULT GETDATE() NULL,
#     [LastUpdBy] VARCHAR(50) CONSTRAINT [DF_InvoiceFileStatus_LastUpdBy] DEFAULT SUSER_NAME() NULL,
#     [LastUpdApp] VARCHAR(250) CONSTRAINT [DF_InvoiceFileStatus_LastUpdApp] DEFAULT APP_NAME() NULL,
#     CONSTRAINT PK_InvoiceFileStatus_InvoiceFileStatusId PRIMARY KEY CLUSTERED (InvoiceFileStatusId)
# ) ON [PRIMARY]
# GO

# CREATE TABLE [dbo].[Invoice](
#     [InvoiceId] INT IDENTITY(1,1) NOT NULL,
#     Vendor INT,
#     PONumber INT,
#     InvoiceNumber VARCHAR(255),
#     InvoiceDate DATE,
#     DueDate DATE,
#     FrghtAmt FLOAT,
#     FrghtCode VARCHAR(255),
#     [Description] VARCHAR(200),
#     CASES DECIMAL(18,2),
#     NET_WEIGHT DECIMAL(18,2),
#     PALLETS DECIMAL(18,2),
#     BOL VARCHAR(255),
#     PARENT_PO VARCHAR(255),
#     COST_PER_UNITS DECIMAL(18,2),
#     CONSIGNEE VARCHAR(200), -- Allows maximum characters
#     InvoiceFileId INT FOREIGN KEY REFERENCES [InvoiceFile]([InvoiceFileId]),
#     [Created] DATETIME CONSTRAINT [DF_Invoice_Created] DEFAULT GETDATE() NULL,
#     [CreatedBy] VARCHAR(50) CONSTRAINT [DF_Invoice_CreatedBy] DEFAULT SUSER_NAME() NULL,
#     [LastUpd] DATETIME CONSTRAINT [DF_Invoice_LastUpd] DEFAULT GETDATE() NULL,
#     [LastUpdBy] VARCHAR(50) CONSTRAINT [DF_Invoice_LastUpdBy] DEFAULT SUSER_NAME() NULL,
#     [LastUpdApp] VARCHAR(250) CONSTRAINT [DF_Invoice_LastUpdApp] DEFAULT APP_NAME() NULL,
#     CONSTRAINT PK_Invoice_InvoiceId PRIMARY KEY CLUSTERED (InvoiceId)
# ) ON [PRIMARY]
# GO

# code example connect to db

# def get_inv_num(vend):
#     print("Connecting to SQL...")
#     server = 'CORPORATE-DW'
#     database = 'AccountsPayable'
#     cnxn = pyodbc.connect('DRIVER={SQL Server}; SERVER='+server+';DATABASE='+database+';trusted_connection=true')
#     cursor = cnxn.cursor()

#     Q = "Select * FROM [AP].[PaymentHistory] AS [PH] (NOLOCK) WHERE [Vendor] = " + vend + " and InvoiceDate >= '2022-01-01'"
#     raw_report = cursor.execute(Q)
#     col_names = [i[0] for i in raw_report.description]
#     results = [i for i in raw_report.fetchall()]
#     raw_report = pd.DataFrame.from_records(results, columns=col_names)
#     return raw_report

# class DBHandler(SQL_Query):u
#     def __init__(self, server='VIRTUALDW', database='LOGISTICS'):
#         super().__init__(server=server, database=database)   
#         self.connect_to_sql()

class DBHandler():
    def __init__(self, server='VIRTUALDW', database='LOGISTICS'):
        self.database = database
        self.server = server 
        # Conns
        self.cnxn = pyodbc.connect('DRIVER={SQL Server}; SERVER='+server+';DATABASE='+database+';trusted_connection=true')
        #self.conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server}; SERVER='+server+';DATABASE='+database+';UID='+self.username+';PWD='+self.password+';trusted_connection=false')
        #self.engine = sqlalchemy.create_engine('DRIVER={SQL Server}; SERVER='+server+';DATABASE='+database+';trusted_connection=true')
        # connection_string = f'mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server'
        # self.engine = sqlalchemy.create_engine(connection_string)
        
    def test_sqlalchemy(self):
        with self.engine.connect() as connection:
            result = connection.execute("SELECT GETDATE()")
            print(result.fetchone())

    def init_invoice_file_status(self):
        """
        Initiate the invoice table.
        """
        # Create file status df
        invoice_file_status = pd.DataFrame({'InvoiceFileStatusId': [1, 2, 3, 4, 5],
                                            'Description': ['Approved', 'Pending', 'Monitoring', 'Rejected', 'Error']})
        self.insert_into_invoicefilestatus(invoice_file_status)

    ### Select functions
    def fetch(self, table, limit=1000):
        """
        Get the data from the table.
        """
        cursor = self.cnxn.cursor()
        Q = "SELECT * FROM [dbo].[{}] (NOLOCK)".format(table)
        raw_report = cursor.execute(Q)
        col_names = [i[0] for i in raw_report.description]
        results = [i for i in raw_report.fetchall()]
        raw_report = pd.DataFrame.from_records(results, columns=col_names)
        return raw_report
    
    ### Insert functions
    def insert_into_invoicefile(self, df):
        """
        Insert into the invoice file table.
        """
        # Create a pyodbc connection
        cursor = self.cnxn.cursor()

        # Define the insert query
        columns = ', '.join(df.columns)
        placeholders = ', '.join('?' * len(df.columns))
        sql = f"INSERT INTO [dbo].[InvoiceFile] ({columns}) VALUES ({placeholders})"

        print('Inserting into the table')
        # Use fast_executemany for efficient bulk insert
        cursor.fast_executemany = True
        print(len(df.values.tolist()))
        cursor.executemany(sql, df.values.tolist())
        cursor.commit()
        cursor.close()
        

    def delete_all_from_table(self, table_name):
        """
        Delete all records from a table.
        """
        sql_command = f'DELETE FROM {table_name}'
        cursor = self.cnxn.cursor()
        cursor.execute(sql_command)
        # Committing the transaction
        cursor.commit()
        # Closing the connection
        cursor.close()


    def insert_into_invoicefilestatus(self, df):
        cursor = self.cnxn.cursor()
        for _, row in df.iterrows():
            cursor.execute("INSERT INTO InvoiceFileStatus (InvoiceFileStatusId, Description) VALUES (?, ?)",
            row['InvoiceFileStatusId'], row['Description'])
        self.cnxn.commit()
        cursor.close()


    def insert_into_invoice(self, df):
        # Create a pyodbc connection
        cursor = self.cnxn.cursor()

        # Define the insert query
        columns = ', '.join(df.columns)
        placeholders = ', '.join('?' * len(df.columns))
        print(columns)
        sql = f"INSERT INTO [dbo].[Invoice] ({columns}) VALUES ({placeholders})"
        print(sql)

        print('Inserting into the table')
        # Use fast_executemany for efficient bulk insert
        cursor.fast_executemany = True
        print(len(df.values.tolist()))
        cursor.executemany(sql, df.values.tolist())
        cursor.commit()
        cursor.close()
        
    def get_AP_from_mainframe(self, vend):
        print("Connecting to SQL...")
        cursor = self.cnxn.cursor()
    
        Q = "Select * FROM [AP].[PaymentHistory] AS [PH] (NOLOCK) WHERE [Vendor] = " + vend + " and InvoiceDate >= '2022-01-01'"
        raw_report = cursor.execute(Q)
        col_names = [i[0] for i in raw_report.description]
        results = [i for i in raw_report.fetchall()]
        raw_report = pd.DataFrame.from_records(results, columns=col_names)
        return raw_report
    
    def get_rows_matching_column_values(self, table, column, ls):
        query = 'SELECT * FROM your_table WHERE InvoiceNumber IN ({})'.format(','.join(['?']*len(ls)))

        # Execute the query and load into a DataFrame
        df = pd.read_sql_query(query, self.cnxn, params=ls)
        return df
    
    def custom_query_select(self, query):
        # Execute the query and load into a DataFrame
        df = pd.read_sql_query(query, self.cnxn)
        return df
    
    def clean_before_push(self, df, round=2):
        '''
            A cleaning script to map the python data types into
        '''
        for col in df.columns:
            if pd.api.types.is_integer_dtype(df[col]):
                print(f"{col} is an int type.")
                df[col] = df[col].astype('Int64')
                # Perform action for int type
            elif pd.api.types.is_float_dtype(df[col]):
                print(f"{col} is a float type.")
                df[col] = df[col].astype('float32')
                df[col] = df[col].round(round)
                # Perform action for float type
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                print(f"{col} is a date type.")
                df[col] = pd.to_datetime(df[col], errors='coerce')
                # Perform action for date type
            else:
                print(f"{col} is not an int, float, or date type.")
                # Perform action for other types
            
        # Turn NaN, inf to None
        df.replace({np.nan: None}, inplace=True)
        df.replace({np.inf: None}, inplace=True)
        df.replace({-np.inf: None}, inplace=True)
        
        return df
    
    def insert_into_table(self, table_name, df):
        # Replace 'your_table' with the actual table name you want to insert data into
        # table_name = 'Ascend_Savings_Report_Audit'
        cursor = self.cnxn.cursor()
        # Preparing column string for the SQL statement
        columns = ', '.join([str(col) for col in df.columns.tolist()])

        # Preparing placeholders for the values
        placeholders = ', '.join(['?' for _ in df.columns])

        # Preparing SQL query
        sql_query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        # Insert DataFrame records one by one.
        #cursor.fast_executemany = True
        # for row in df_test.values.tolist():
        #     print(row)
        #     cursor.execute(sql_query, row)
        tmp = df.values.tolist()
        for l in tmp:
        
            cursor.execute(sql_query, l)
        
        # Commit the transaction
        self.cnxn.commit()

        
    # def _get_file_id(self, fpath):
    #     """
    #         Get the auto assigned file id after file added to the table. 
    #     """
    #     try:
    #         dbh = DBHandler(self.server, self.database)
    #         query = f"""
    #                     SELECT InvoiceFileId
    #                     FROM InvoiceFile I
    #                     WHERE I.FilePath = '{fpath}'
    #                 """
    #         print(query)
    #         cursor = dbh.conn.cursor()
    #         raw_report = cursor.execute(query)
    #         results = [i for i in raw_report.fetchall()]

    #     finally:
    #         dbh.close()
            
    #     return results[0][0]

            
    # def _update_file_status(self, status, file_id):
    #     """
    #         Update the status on a file table.
    #     """
    #     try:
    #         dbh = DBHandler(self.server, self.database)
            
    #         query = f"""
    #                     UPDATE InvoiceFile
    #                     SET InvoiceFileStatusId = {str(status)}
    #                     WHERE InvoiceFileId = {str(file_id)};
    #                 """
    #         print(query)
    #         cursor = dbh.conn.cursor()
            
    #         cursor.execute(query)
    #         cursor.commit()
            
    #     finally:
    #         dbh.close

    def close(self):
        self.cnxn.close()
        #self.engine.dispose()