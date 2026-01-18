#!/usr/bin/env python3
"""
Fix duplicate RLS policies in Supabase.
This script connects to Supabase and removes duplicate policies.
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def get_db_connection():
    """Get database connection from Supabase connection string."""
    # Try to get from environment
    db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    
    if not db_url:
        # Try to construct from Supabase URL and key
        supabase_url = os.getenv("SUPABASE_URL")
        if supabase_url:
            # Extract project ref from URL
            # Format: https://<project_ref>.supabase.co
            project_ref = supabase_url.replace("https://", "").replace(".supabase.co", "")
            db_password = os.getenv("SUPABASE_DB_PASSWORD") or os.getenv("SUPABASE_PASSWORD")
            
            if db_password:
                db_url = f"postgresql://postgres.{project_ref}:{db_password}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    
    if not db_url:
        print("❌ Error: No database connection string found.")
        print("Set SUPABASE_DB_URL or DATABASE_URL environment variable.")
        print("Or set SUPABASE_URL and SUPABASE_DB_PASSWORD")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(db_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)

def execute_sql_file(conn, filepath):
    """Execute SQL file."""
    with open(filepath, 'r') as f:
        sql = f.read()
    
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        cursor.close()
        print(f"✅ Successfully executed migration: {filepath}")
        return True
    except Exception as e:
        print(f"❌ Error executing SQL: {e}")
        return False

def main():
    """Main function."""
    migration_file = os.path.join(
        os.path.dirname(__file__),
        "agents/supabase/migrations/20260114_fix_duplicate_rls_policies.sql"
    )
    
    if not os.path.exists(migration_file):
        print(f"❌ Migration file not found: {migration_file}")
        sys.exit(1)
    
    print("🔌 Connecting to Supabase database...")
    conn = get_db_connection()
    
    print("📝 Executing migration to fix duplicate RLS policies...")
    success = execute_sql_file(conn, migration_file)
    
    conn.close()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("All duplicate RLS policies have been removed and consolidated.")
    else:
        print("\n❌ Migration failed. Check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
