"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import SignUpModal from "./components/SignUpModal";
import SubscriptionModal from "./components/SubscriptionModal";

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
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false);
  const [guestMessageCount, setGuestMessageCount] = useState(0);

  // Load messages and guest message count from localStorage on mount
  useEffect(() => {
    const fetchMessages = async () => {
      try {
        const response = await fetch("/api/chat");
        if (!response.ok) {
          throw new Error("Failed to fetch messages");
        }
        const data = await response.json();
        setMessages(data.messages.map((msg: any) => ({
          id: msg.id.toString(),
          content: msg.content,
          role: msg.role,
        })));
      } catch (error) {
        console.error("Error fetching messages:", error);
      }
    };

    fetchMessages();
    
    const count = localStorage.getItem("guestMessageCount");
    if (count) {
      setGuestMessageCount(parseInt(count));
    }
  }, []);

  const resetChat = async () => {
    try {
      const response = await fetch("/api/chat", {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to clear messages");
      }

      // Clear messages state
      setMessages([]);
      // Reset guest message count
      setGuestMessageCount(0);
      localStorage.removeItem("guestMessageCount");
      // Reset signup modal
      setShowSignUpModal(false);
    } catch (error) {
      console.error("Error resetting chat:", error);
    }
  };

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

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ content: input }),
      });

      if (!response.ok) {
        throw new Error("Failed to send message");
      }

      const data = await response.json();
      
      if (response.status === 403 && data.requiresSubscription) {
        setShowSubscriptionModal(true);
        return;
      }

      // Add the bot response to messages
      setMessages((prev) => [
        ...prev,
        {
          id: data.messages[1].id.toString(),
          content: data.messages[1].content,
          role: "assistant",
        },
      ]);
    } catch (error) {
      console.error("Error sending message:", error);
      // Add error message to chat
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          content: "Sorry, there was an error processing your message.",
          role: "assistant",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
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
              <div className="flex items-center space-x-2">
            <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
          </div>
            </div>
          </div>
        )}
      </div>
      <form onSubmit={sendMessage} className="border-t bg-white p-4">
        <div className="flex justify-end mb-2">
          <button
            type="button"
            onClick={resetChat}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Clear Chat
          </button>
        </div>
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
      <SubscriptionModal
        isOpen={showSubscriptionModal}
        onClose={() => setShowSubscriptionModal(false)}
      />
    </div>
  );
}
