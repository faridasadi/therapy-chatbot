import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "../auth/[...nextauth]/route";
import db from "@/lib/db";

export async function DELETE() {
  try {
    const session = await getServerSession(authOptions);
    const userId = session?.user ? parseInt(session.user.id) : undefined;
    
    await db.clearMessages(userId);
    return NextResponse.json({ message: "Messages cleared successfully" });
  } catch (error) {
    console.error("Error clearing messages:", error);
    return NextResponse.json(
      { error: "Failed to clear messages" },
      { status: 500 }
    );
  }
}

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
    const userId = session?.user ? parseInt(session.user.id) : undefined;

    // Check message limit for authenticated users
    if (userId) {
      const canSendMessage = await db.checkMessageLimit(userId);
      if (!canSendMessage) {
        return NextResponse.json({
          error: "Weekly message limit reached. Please subscribe to continue.",
          requiresSubscription: true
        }, { status: 403 });
      }
      await db.updateWeeklyMessageCount(userId);
    }

    // Save user message
    const userMessage = await db.createMessage(
      content,
      "user",
      userId
    );

    // TODO: Integrate with actual AI service
    // For now, return a simple response
    const botResponse = await db.createMessage(
      "Thank you for your message. I am here to help.",
      "assistant",
      userId
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
