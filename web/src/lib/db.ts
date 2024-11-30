import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

export interface User {
  id: number;
  email: string;
  name: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface Message {
  id: number;
  content: string;
  role: 'user' | 'assistant';
  user_id: number | null;
  created_at: Date;
}

export const db = {
  async getUserByEmail(email: string) {
    const result = await pool.query<User>(
      'SELECT * FROM users WHERE email = $1',
      [email]
    );
    return result.rows[0];
  },

  async createUser(email: string, hashedPassword: string, name?: string) {
    const result = await pool.query<User>(
      'INSERT INTO users (email, password, name) VALUES ($1, $2, $3) RETURNING *',
      [email, hashedPassword, name]
    );
    return result.rows[0];
  },

  async getUserMessages(userId: number) {
    const result = await pool.query<Message>(
      'SELECT * FROM messages WHERE user_id = $1 ORDER BY created_at ASC',
      [userId]
    );
    return result.rows;
  },

  async createMessage(content: string, role: 'user' | 'assistant', userId?: number) {
    const result = await pool.query<Message>(
      'INSERT INTO messages (content, role, user_id) VALUES ($1, $2, $3) RETURNING *',
      [content, role, userId]
    );
    return result.rows[0];
  },
};

export default db;
