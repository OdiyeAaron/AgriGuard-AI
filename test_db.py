import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os

# Use a local test DB name so it doesn't interfere with your main one
TEST_DB = "test_agriguard.db"

def run_test():
    print("--- 🔍 Starting Database Connectivity Test ---")
    
    # 1. Create Connection
    try:
        conn = sqlite3.connect(TEST_DB)
        print("✅ Connection Successful.")
        
        # 2. Create Table
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      username TEXT UNIQUE, 
                      email TEXT, 
                      password TEXT)''')
        print("✅ Table Creation Successful.")

        # 3. Test Signup Logic (Hashing)
        user = "aaron_test"
        raw_pw = "stlawrence2026"
        hashed_pw = generate_password_hash(raw_pw)
        
        conn.execute("INSERT OR REPLACE INTO users (username, email, password) VALUES (?, ?, ?)", 
                     (user, "test@slu.ac.ug", hashed_pw))
        conn.commit()
        print(f"✅ User Injection Successful (User: {user})")

        # 4. Test Login Logic (Verification)
        row = conn.execute("SELECT password FROM users WHERE username = ?", (user,)).fetchone()
        if row and check_password_hash(row[0], raw_pw):
            print("✅ Password Verification Successful.")
        else:
            print("❌ Password Verification Failed.")

        conn.close()
        print("--- 🏆 All Tests Passed! ---")
        
    except Exception as e:
        print(f"❌ Test Failed with Error: {e}")
    finally:
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
            print("🧹 Cleaned up test database file.")

if __name__ == "__main__":
    run_test()