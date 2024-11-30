"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

const signInSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

type SignInData = z.infer<typeof signInSchema>;

export default function SignIn() {
  const [error, setError] = useState<string>("");
  const { register, handleSubmit, formState: { errors } } = useForm<SignInData>({
    resolver: zodResolver(signInSchema),
  });

  const onSubmit = async (data: SignInData) => {
    try {
      const result = await signIn("credentials", {
        ...data,
        redirect: false,
      });

      if (result?.error) {
        setError("Invalid credentials");
      }
    } catch (err) {
      setError("An error occurred. Please try again.");
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center">
      <div className="w-full max-w-md space-y-8 rounded-lg bg-white p-6 shadow-lg">
        <div>
          <h2 className="text-center text-3xl font-bold tracking-tight">
            Sign in to your account
          </h2>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit(onSubmit)}>
          <div className="space-y-4 rounded-md">
            <div>
              <label htmlFor="email" className="sr-only">
                Email address
              </label>
              <input
                {...register("email")}
                type="email"
                className="relative block w-full rounded-lg border p-3"
                placeholder="Email address"
              />
              {errors.email && (
                <p className="mt-1 text-sm text-red-500">{errors.email.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <input
                {...register("password")}
                type="password"
                className="relative block w-full rounded-lg border p-3"
                placeholder="Password"
              />
              {errors.password && (
                <p className="mt-1 text-sm text-red-500">{errors.password.message}</p>
              )}
            </div>
          </div>

          {error && (
            <div className="text-center text-sm text-red-500">{error}</div>
          )}

          <button
            type="submit"
            className="group relative flex w-full justify-center rounded-lg bg-blue-600 px-4 py-3 text-sm font-medium text-white hover:bg-blue-700"
          >
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
}
