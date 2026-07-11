import type { ChatMessage } from "./api";

export type ChatSubmission = {
  message: string;
  messages: ChatMessage[];
};

export function createChatSubmission(input: {
  prompt: string;
  messages: ChatMessage[];
  isSending: boolean;
}): ChatSubmission | null;
