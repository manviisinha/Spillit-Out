import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "confession_bot.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        print("Starting migration...")
        
        # Check if target_description exists in existing confessions table
        # If not, the previous ALTER TABLE might have failed or not run
        cursor = conn.execute("PRAGMA table_info(confessions)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        if 'target_description' not in columns:
            print("Adding target_description column to existing table first...")
            conn.execute("ALTER TABLE confessions ADD COLUMN target_description TEXT")
            
        print("Creating new table...")
        # Create new table
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS confessions_new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id           INTEGER NOT NULL,
                receiver_id         INTEGER,
                target_description  TEXT,
                message             TEXT,
                media_type          TEXT,
                media_file_id       TEXT,
                status              TEXT    DEFAULT 'pending',
                group_msg_id        INTEGER,
                created_at          TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(sender_id) REFERENCES users(telegram_id)
            );
            
            INSERT INTO confessions_new (id, sender_id, receiver_id, target_description, message, media_type, media_file_id, status, group_msg_id, created_at)
            SELECT id, sender_id, receiver_id, target_description, message, media_type, media_file_id, status, group_msg_id, created_at FROM confessions;
            
            DROP TABLE confessions;
            ALTER TABLE confessions_new RENAME TO confessions;
            
            CREATE INDEX IF NOT EXISTS idx_confessions_receiver ON confessions(receiver_id);
            CREATE INDEX IF NOT EXISTS idx_confessions_sender   ON confessions(sender_id);
            CREATE INDEX IF NOT EXISTS idx_confessions_status   ON confessions(status);
        """)
        conn.commit()
        print("Migration successful")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
