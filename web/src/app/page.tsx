"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";

interface Message {
  id: string;
  content: string;
  role: "user" | "assistant";
}

export default function Home() {
  const { data: session } = useSession();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const newMessage: Message = {
      id: Date.now().toString(),
      content: input,
      role: "user",
    };

    setMessages((prev) => [...prev, newMessage]);
    setInput("");
    setIsLoading(true);

    // TODO: Implement API call for chat response
    setIsLoading(false);
  };

  return (
    <div className="flex h-screen flex-col bg-gray-100">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${
              message.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[70%] rounded-lg p-4 ${
                message.role === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-white text-gray-900"
              }`}
            >
              {message.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white rounded-lg p-4">
              <div className="animate-pulse">Thinking...</div>
            </div>
          </div>
        )}
      </div>
      <form onSubmit={sendMessage} className="border-t bg-white p-4">
        <div className="flex space-x-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 rounded-lg border p-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={isLoading}
            className="rounded-lg bg-blue-500 px-4 py-2 text-white hover:bg-blue-600 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
