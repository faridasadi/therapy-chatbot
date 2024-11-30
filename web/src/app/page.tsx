"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import SignUpModal from "./components/SignUpModal";

interface Message {
  id: string;
  content: string;
  role: "user" | "assistant";
}

const MAX_GUEST_MESSAGES = 5;

export default function Home() {
  const { data: session } = useSession();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showSignUpModal, setShowSignUpModal] = useState(false);
  const [guestMessageCount, setGuestMessageCount] = useState(0);

  // Load guest message count from localStorage on mount
  useEffect(() => {
    const count = localStorage.getItem("guestMessageCount");
    if (count) {
      setGuestMessageCount(parseInt(count));
    }
  }, []);

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    // Check if user has reached guest message limit
    if (!session && guestMessageCount >= MAX_GUEST_MESSAGES) {
      setShowSignUpModal(true);
      return;
    }

    const newMessage: Message = {
      id: Date.now().toString(),
      content: input,
      role: "user",
    };

    setMessages((prev) => [...prev, newMessage]);
    setInput("");
    setIsLoading(true);

    if (!session) {
      const newCount = guestMessageCount + 1;
      setGuestMessageCount(newCount);
      localStorage.setItem("guestMessageCount", newCount.toString());
      
      if (newCount >= MAX_GUEST_MESSAGES) {
        setShowSignUpModal(true);
      }
    }

    // TODO: Implement API call for chat response
    // Simulate API response for now
    setTimeout(() => {
      const botResponse: Message = {
        id: Date.now().toString(),
        content: "This is a simulated response. Please sign up to chat with the AI.",
        role: "assistant",
      };
      setMessages((prev) => [...prev, botResponse]);
      setIsLoading(false);
    }, 1000);
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
      <SignUpModal 
        isOpen={showSignUpModal} 
        onClose={() => setShowSignUpModal(false)} 
      />
    </div>
  );
}
