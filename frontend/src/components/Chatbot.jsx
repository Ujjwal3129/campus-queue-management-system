import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
    MessageSquare, 
    X, 
    Send, 
    Bot, 
    User, 
    MinusCircle, 
    RefreshCcw,
    Sparkles
} from 'lucide-react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';

// ─────────────────────────────────────────────────────────────────────────────
// TYPEWRITER CONFIG  — tweak these two numbers to change typing speed
// ─────────────────────────────────────────────────────────────────────────────
const CHAR_DELAY_MS = 16;   // milliseconds between each tick  (lower = faster)
const CHUNK_SIZE    = 3;    // characters revealed per tick     (higher = faster)

// ─────────────────────────────────────────────────────────────────────────────
// useTypewriter
// Streams `fullText` into a `displayed` string chunk-by-chunk.
// Only active when `isActive` is true.  Calls `onDone` when finished.
// ─────────────────────────────────────────────────────────────────────────────
function useTypewriter(fullText, isActive, onDone) {
    const [displayed, setDisplayed] = useState('');
    const indexRef = useRef(0);
    const timerRef = useRef(null);

    useEffect(() => {
        if (!isActive || !fullText) return;

        // Reset for each new message
        setDisplayed('');
        indexRef.current = 0;

        const tick = () => {
            if (indexRef.current >= fullText.length) {
                onDone?.();
                return;
            }
            const next = Math.min(indexRef.current + CHUNK_SIZE, fullText.length);
            setDisplayed(fullText.slice(0, next));
            indexRef.current = next;
            timerRef.current = setTimeout(tick, CHAR_DELAY_MS);
        };

        timerRef.current = setTimeout(tick, CHAR_DELAY_MS);
        return () => clearTimeout(timerRef.current);
    }, [fullText, isActive]); // eslint-disable-line react-hooks/exhaustive-deps

    return displayed;
}

// ─────────────────────────────────────────────────────────────────────────────
// MARKDOWN-LITE RENDERER
// Handles **bold**, *italic*, `code`, bullet lists (- or •)
// Keeps the same text-sm sizing your existing bubbles use
// ─────────────────────────────────────────────────────────────────────────────
function inlineFormat(text) {
    const parts = [];
    const rx = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
    let last = 0, m;
    while ((m = rx.exec(text)) !== null) {
        if (m.index > last) parts.push(text.slice(last, m.index));
        if (m[2]) parts.push(<strong key={m.index}>{m[2]}</strong>);
        else if (m[3]) parts.push(<em key={m.index}>{m[3]}</em>);
        else if (m[4]) parts.push(
            <code key={m.index} className="bg-white/10 rounded px-1 font-mono text-[0.82em]">
                {m[4]}
            </code>
        );
        last = m.index + m[0].length;
    }
    if (last < text.length) parts.push(text.slice(last));
    return parts.length ? parts : text;
}

function renderMarkdown(text) {
    if (!text) return null;
    const lines  = text.split('\n');
    const els    = [];
    let listBuf  = [];

    const flushList = (key) => {
        if (!listBuf.length) return;
        els.push(
            <ul key={`ul-${key}`} className="list-disc list-inside space-y-0.5 my-1">
                {listBuf.map((item, i) => (
                    <li key={i}>{inlineFormat(item)}</li>
                ))}
            </ul>
        );
        listBuf = [];
    };

    lines.forEach((line, i) => {
        const t = line.trim();
        if (/^[-•*]\s/.test(t))      listBuf.push(t.replace(/^[-•*]\s/, ''));
        else if (/^\d+\.\s/.test(t)) listBuf.push(t.replace(/^\d+\.\s/, ''));
        else {
            flushList(i);
            if (t === '') els.push(<div key={i} className="h-1.5" />);
            else          els.push(<p key={i} className="leading-relaxed">{inlineFormat(t)}</p>);
        }
    });
    flushList('end');
    return els;
}

// ─────────────────────────────────────────────────────────────────────────────
// SINGLE MESSAGE  — bot messages animate via useTypewriter when streaming
// ─────────────────────────────────────────────────────────────────────────────
function MessageBubble({ msg, isStreaming, onStreamDone, onOptionClick }) {
    const isBot   = msg.sender === 'bot';
    const visible = useTypewriter(msg.text, isStreaming && isBot, onStreamDone);
    const text    = (isStreaming && isBot) ? visible : msg.text;

    // Show options only after typewriter finishes (or instantly for old messages)
    const showOptions = msg.options?.length > 0 && (!isStreaming || visible.length >= msg.text.length);

    return (
        <motion.div
            initial={{ opacity: 0, x: msg.sender === 'user' ? 20 : -20 }}
            animate={{ opacity: 1, x: 0 }}
            className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
        >
            <div className={`flex gap-2 max-w-[85%] ${msg.sender === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                {/* Avatar */}
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                    msg.sender === 'user'
                        ? 'bg-[var(--accent-primary)]'
                        : 'bg-[var(--bg-tertiary)] border border-[var(--glass-border)]'
                }`}>
                    {msg.sender === 'user' ? <User size={16} /> : <Bot size={16} />}
                </div>

                <div className="space-y-2">
                    {/* Bubble */}
                    <div className={`p-3 rounded-2xl text-sm shadow-sm ${
                        msg.sender === 'user'
                            ? 'bg-[var(--accent-primary)] text-white rounded-tr-none'
                            : 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--glass-border)] rounded-tl-none'
                    }`}>
                        {renderMarkdown(text)}

                        {/* Blinking cursor shown while the typewriter is still running */}
                        {isStreaming && isBot && visible.length < msg.text.length && (
                            <span className="inline-block w-[2px] h-[1em] bg-current align-middle ml-0.5 animate-pulse" />
                        )}
                    </div>

                    {/* Quick-reply options — fade in once typing is done */}
                    {showOptions && (
                        <motion.div
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.2 }}
                            className="flex flex-wrap gap-2 pt-1"
                        >
                            {msg.options.map((opt, i) => (
                                <button
                                    key={i}
                                    onClick={() => onOptionClick(opt.value)}
                                    className="text-xs py-1.5 px-3 rounded-full bg-[var(--bg-tertiary)] border border-[var(--glass-border)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)] transition-all duration-300 font-medium"
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </motion.div>
                    )}
                </div>
            </div>
        </motion.div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN CHATBOT COMPONENT  — your original structure, unchanged
// ─────────────────────────────────────────────────────────────────────────────
const Chatbot = () => {
    const [isOpen, setIsOpen]       = useState(false);
    const [messages, setMessages]   = useState([
        {
            id: 0,
            text: "Hi! I'm your Campus AI. I can help you check your ticket status, list departments, or find the best time to visit. What can I do for you?",
            sender: 'bot',
            options: [
                { label: '🎟️ My Ticket',  value: 'my ticket status' },
                { label: '🏢 Departments', value: 'list departments' },
                { label: '🚦 Queue Status', value: 'is it busy' }
            ]
        }
    ]);
    const [input,       setInput]       = useState('');
    const [loading,     setLoading]     = useState(false);
    const [streamingId, setStreamingId] = useState(null); // id of the message currently typing

    const messagesEndRef = useRef(null);
    const inputRef       = useRef(null);
    const msgCounter     = useRef(1);

    // ── Auto-scroll whenever messages change or typewriter updates ────────
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };
    useEffect(scrollToBottom, [messages, streamingId]);

    // ── Called when typewriter finishes ──────────────────────────────────
    const handleStreamDone = useCallback(() => {
        setStreamingId(null);
        inputRef.current?.focus();
    }, []);

    // ── Core send logic (unchanged API call, new streaming state) ─────────
    const handleSend = async (text = input) => {
        if (!text.trim() || loading || streamingId) return;

        const userMessage = { id: ++msgCounter.current, text, sender: 'user' };
        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setLoading(true);

        try {
            const token       = localStorage.getItem('token');
            const storedUser  = JSON.parse(localStorage.getItem('user') || '{}');
            let   role        = storedUser.role   || localStorage.getItem('role')       || 'guest';
            let   userId      = storedUser.id     || storedUser._id
                              || localStorage.getItem('guestToken') || 'anonymous';

            if (token && (userId === 'anonymous' || !userId)) {
                try {
                    const base64Url  = token.split('.')[1];
                    const base64     = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                    const jsonPayload = decodeURIComponent(
                        atob(base64).split('').map(c =>
                            '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
                        ).join('')
                    );
                    userId = JSON.parse(jsonPayload).id;
                } catch (e) {
                    console.error('Token decode error:', e);
                }
            }

            const response = await axios.post(
                `${import.meta.env.VITE_API_URL}/chatbot/query`,
                { message: text, userId, role }
            );

            // Add bot message with full text — typewriter reveals it gradually
            const botId = ++msgCounter.current;
            const botMessage = {
                id:      botId,
                text:    response.data.response,
                sender:  'bot',
                options: response.data.options || []
            };

            setMessages(prev => [...prev, botMessage]);
            setStreamingId(botId);       // ← starts the typewriter

        } catch (error) {
            console.error('Chatbot error:', error);
            const errId = ++msgCounter.current;
            setMessages(prev => [...prev, {
                id:     errId,
                text:   "Sorry, I'm having trouble connecting to the server. Please try again later.",
                sender: 'bot'
            }]);
            setStreamingId(errId);
        } finally {
            setLoading(false);
        }
    };

    const handleOptionClick = (optionValue) => {
        if (loading || streamingId) return;   // ignore taps while bot is typing
        handleSend(optionValue);
    };

    const isLocked = loading || !!streamingId;

    return (
        <div className="fixed bottom-6 right-6 z-[9999]">

            {/* ── Floating button ── */}
            <AnimatePresence>
                {!isOpen && (
                    <motion.button
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0, opacity: 0 }}
                        onClick={() => setIsOpen(true)}
                        className="bg-[var(--accent-primary)] text-white p-4 rounded-full shadow-2xl hover:scale-110 transition-transform flex items-center justify-center group relative overflow-hidden"
                    >
                        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                        <MessageSquare size={28} />
                    </motion.button>
                )}
            </AnimatePresence>

            {/* ── Chat window ── */}
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, y: 100, scale: 0.9 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 100, scale: 0.9 }}
                        className="bg-[var(--bg-secondary)] border border-[var(--glass-border)] w-[380px] h-[550px] rounded-2xl shadow-2xl flex flex-col overflow-hidden backdrop-blur-xl"
                    >
                        {/* Header — unchanged */}
                        <div className="bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)] p-4 text-white flex justify-between items-center shadow-lg">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-white/20 rounded-lg">
                                    <Sparkles size={20} className="animate-pulse" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-sm">Campus Assistant</h3>
                                    <div className="flex items-center gap-1.5">
                                        <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                                        <span className="text-[10px] opacity-80 font-medium uppercase tracking-wider">AI Powered</span>
                                    </div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => {
                                        setMessages([messages[0]]);
                                        setStreamingId(null);
                                    }}
                                    className="hover:bg-white/20 p-1.5 rounded-lg transition-colors"
                                    title="Reset Chat"
                                >
                                    <RefreshCcw size={18} />
                                </button>
                                <button
                                    onClick={() => setIsOpen(false)}
                                    className="hover:bg-white/20 p-1.5 rounded-lg transition-colors"
                                >
                                    <X size={18} />
                                </button>
                            </div>
                        </div>

                        {/* Messages area */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar bg-[var(--bg-primary)]/30">
                            {messages.map((msg) => (
                                <MessageBubble
                                    key={msg.id}
                                    msg={msg}
                                    isStreaming={msg.id === streamingId}
                                    onStreamDone={handleStreamDone}
                                    onOptionClick={handleOptionClick}
                                />
                            ))}

                            {/* Typing indicator — shown only while waiting for the API */}
                            {loading && (
                                <div className="flex justify-start">
                                    <div className="flex gap-2 max-w-[85%]">
                                        {/* Bot avatar */}
                                        <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-[var(--bg-tertiary)] border border-[var(--glass-border)]">
                                            <Bot size={16} />
                                        </div>
                                        {/* Bouncing dots */}
                                        <div className="bg-[var(--bg-tertiary)] border border-[var(--glass-border)] p-3 rounded-2xl rounded-tl-none flex items-center gap-1.5">
                                            <span className="w-1.5 h-1.5 bg-[var(--text-secondary)] rounded-full animate-bounce" />
                                            <span className="w-1.5 h-1.5 bg-[var(--text-secondary)] rounded-full animate-bounce [animation-delay:0.2s]" />
                                            <span className="w-1.5 h-1.5 bg-[var(--text-secondary)] rounded-full animate-bounce [animation-delay:0.4s]" />
                                            <span className="text-[11px] text-[var(--text-secondary)] ml-1 opacity-70">
                                                Thinking…
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div ref={messagesEndRef} />
                        </div>

                        {/* Input area — unchanged */}
                        <form
                            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
                            className="p-4 bg-[var(--bg-secondary)] border-t border-[var(--glass-border)] flex gap-2"
                        >
                            <input
                                ref={inputRef}
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder={isLocked ? 'Please wait…' : 'Ask about queues...'}
                                disabled={isLocked}
                                className="flex-1 bg-[var(--bg-tertiary)] border border-[var(--glass-border)] rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent-primary)] transition-colors text-[var(--text-primary)] disabled:opacity-50"
                            />
                            <button
                                type="submit"
                                disabled={isLocked}
                                className="bg-[var(--accent-primary)] text-white p-2 rounded-xl hover:bg-[var(--accent-secondary)] transition-colors disabled:opacity-50"
                            >
                                <Send size={20} />
                            </button>
                        </form>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default Chatbot;