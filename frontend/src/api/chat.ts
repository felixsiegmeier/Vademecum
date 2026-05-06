interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export async function getChatHistory(patientId: string): Promise<ChatMessage[]> {
  try {
    const res = await fetch(`/api/chat/${patientId}`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.messages as ChatMessage[]) ?? [];
  } catch {
    return [];
  }
}

export async function saveChatHistory(patientId: string, messages: ChatMessage[]): Promise<void> {
  try {
    await fetch(`/api/chat/${patientId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
  } catch {
    // fire-and-forget — non-blocking
  }
}

export async function deleteChatHistory(patientId: string): Promise<void> {
  await fetch(`/api/chat/${patientId}`, { method: "DELETE" });
}
