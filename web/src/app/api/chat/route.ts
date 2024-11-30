import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "../auth/[...nextauth]/route";
import db from "@/lib/db";

export async function GET() {
  try {
    const session = await getServerSession(authOptions);
    const userId = session?.user ? parseInt(session.user.id) : undefined;
    const messages = await db.getMessages(userId);
    
    return NextResponse.json({ messages });
  } catch (error) {
    console.error("Error fetching messages:", error);
    return NextResponse.json(
      { error: "Failed to fetch messages" },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  const session = await getServerSession(authOptions);
  const { content } = await request.json();

  if (!content) {
    return NextResponse.json({ error: "Message content is required" }, { status: 400 });
  }

  try {
    // Save user message
    const userMessage = await db.createMessage(
      content,
      "user",
      session?.user ? parseInt(session.user.id) : undefined
    );

    // TODO: Integrate with actual AI service
    // For now, return a simple response
    const botResponse = await db.createMessage(
      "Thank you for your message. I am here to help.",
      "assistant",
      session?.user ? parseInt(session.user.id) : undefined
    );

    return NextResponse.json({
      messages: [userMessage, botResponse]
    });
  } catch (error) {
    console.error("Error processing chat message:", error);
    return NextResponse.json(
      { error: "Failed to process message" },
      { status: 500 }
    );
  }
}
