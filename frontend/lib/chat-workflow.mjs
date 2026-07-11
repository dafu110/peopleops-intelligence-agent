export function createChatSubmission({ prompt, messages, isSending }) {
  const message = prompt.trim();
  if (!message || isSending) return null;

  return {
    message,
    messages: [...messages, { role: "user", content: message }],
  };
}
