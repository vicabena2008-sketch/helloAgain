import sqlite3

con = sqlite3.connect('helloagain.db')
con.execute("UPDATE customers SET tag='active' WHERE tag='hot'")
con.execute("UPDATE customers SET tag='follow_up' WHERE tag='warm'")
con.execute("UPDATE customers SET tag='recoverable' WHERE tag='inactive'")
con.execute("UPDATE customers SET tag='normal' WHERE tag='new'")
con.commit()
print('Migration complete.')
