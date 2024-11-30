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
  weekly_message_count: number;
  weekly_reset_date: Date;
  is_subscribed: boolean;
  subscription_ends: Date | null;
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

  async getMessages(userId?: number) {
    const query = userId 
      ? 'SELECT * FROM messages WHERE user_id = $1 ORDER BY created_at ASC'
      : 'SELECT * FROM messages WHERE user_id IS NULL ORDER BY created_at ASC LIMIT 50';
    
    const result = await pool.query<Message>(
      query,
      userId ? [userId] : []
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

  async clearMessages(userId?: number) {
    const query = userId
      ? 'DELETE FROM messages WHERE user_id = $1'
      : 'DELETE FROM messages WHERE user_id IS NULL';
    await pool.query(query, userId ? [userId] : []);
  async updateWeeklyMessageCount(userId: number) {
    const result = await pool.query<User>(
      `UPDATE users 
       SET weekly_message_count = CASE 
         WHEN weekly_reset_date < NOW() - INTERVAL '7 days' 
         THEN 1 
         ELSE weekly_message_count + 1 
       END,
       weekly_reset_date = CASE 
         WHEN weekly_reset_date < NOW() - INTERVAL '7 days' 
         THEN NOW() 
         ELSE weekly_reset_date 
       END
       WHERE id = $1
       RETURNING *`,
      [userId]
    );
    return result.rows[0];
  },

  async checkMessageLimit(userId: number): Promise<boolean> {
    const result = await pool.query<User>(
      `SELECT weekly_message_count, weekly_reset_date, is_subscribed, subscription_ends 
       FROM users 
       WHERE id = $1`,
      [userId]
    );
    
    const user = result.rows[0];
    if (!user) return false;

    // Reset weekly count if a week has passed
    if (user.weekly_reset_date < new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)) {
      return true;
    }

    // Subscribed users have unlimited messages
    if (user.is_subscribed && user.subscription_ends && user.subscription_ends > new Date()) {
      return true;
    }

    // Non-subscribed users have 20 messages per week limit
    return user.weekly_message_count < 20;
  },
  },
};

export default db;
