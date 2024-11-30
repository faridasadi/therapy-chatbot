"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";

interface SignUpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SignUpModal({ isOpen, onClose }: SignUpModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg p-6 max-w-md w-full">
        <h2 className="text-2xl font-bold mb-4">Continue Chatting</h2>
        <p className="mb-4">
          Sign up to continue chatting and access more features!
        </p>
        <div className="flex justify-end space-x-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 hover:text-gray-800"
          >
            Maybe Later
          </button>
          <button
            onClick={() => signIn(undefined, { callbackUrl: "/" })}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
          >
            Sign Up
          </button>
        </div>
      </div>
    </div>
  );
}
