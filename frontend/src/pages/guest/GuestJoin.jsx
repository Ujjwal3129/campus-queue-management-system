import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../../services/api";
import toast from "react-hot-toast";

export default function GuestJoin() {
  /* ==========================
     DEBUG – CONFIRM FILE LOAD
  ========================== */
  console.log("🔥 GUEST JOIN FILE LOADED 🔥");

  /* ==========================
     ROUTER HOOKS
  ========================== */
  const { sessionToken } = useParams();
  const navigate = useNavigate();

  /* ==========================
     FORM STATE
  ========================== */
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [showPayment, setShowPayment] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  /* ==========================
     ENSURE GUEST IS ANONYMOUS
  ========================== */
  useEffect(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
  }, []);

  /* ==========================
     SESSION TOKEN GUARD
  ========================== */
  useEffect(() => {
    if (!sessionToken) {
      setMessage("Invalid or expired session");
    }
  }, [sessionToken]);

  /* ==========================
     JOIN QUEUE (SESSION BASED)
  ========================== */
  const handleJoin = async () => {
    if (!sessionToken) return;
    setShowPayment(true);
  };

  const executeJoin = async () => {
    try {
      setLoading(true);
      setMessage("");

      const guestToken = localStorage.getItem("guestToken");

      const res = await api.post(
        `/guest/join/${sessionToken}`,
        { name, phone },
        {
          headers: guestToken ? { "x-guest-token": guestToken } : {},
          withCredentials: true,
        }
      );

      // Store guest token for restore/cancel
      if (res.data.guestToken) {
        localStorage.setItem("guestToken", res.data.guestToken);
      }

      toast.success("your queue ticket is created");
      navigate("/guest/ticket");
    } catch (err) {
      setMessage(
        err.response?.data?.message ||
          "Failed to join queue. Please try again."
      );
      setShowPayment(false);
    } finally {
      setLoading(false);
    }
  };

  /* ==========================
     AUTO DISMISS MESSAGE
  ========================== */
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(""), 5000);
    return () => clearTimeout(t);
  }, [message]);

  /* ==========================
     UI
  ========================== */
  return (
    <div className="relative min-h-screen flex items-center justify-center px-4 overflow-hidden text-slate-100">
      {/* BACKGROUND */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#0a1330] via-[#0f1f4d] to-[#141b3a]" />

      {/* GLOWS */}
      <div className="absolute -top-40 -left-40 w-[500px] h-[500px] bg-violet-600/25 rounded-full blur-3xl" />
      <div className="absolute bottom-0 -right-40 w-[400px] h-[400px] bg-indigo-600/25 rounded-full blur-3xl" />

      {/* CARD */}
      <div className="relative z-10 w-full max-w-md rounded-3xl bg-white/5 backdrop-blur-xl border border-white/10 px-8 py-10 shadow-[0_30px_90px_rgba(0,0,0,0.55)]">
        
        {!showPayment ? (
          <>
            {/* LOGO */}
            <div className="flex flex-col items-center mb-8">
              <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-lg mb-3">
                CF
              </div>
              <h2 className="text-xl font-bold text-blue-100">
                QueueFlow
              </h2>
            </div>

            {/* HEADER */}
            <div className="text-center mb-8">
              <h1 className="text-2xl font-semibold bg-gradient-to-r from-violet-400 via-fuchsia-400 to-indigo-400 bg-clip-text text-transparent">
                Join Queue
              </h1>
              <p className="text-slate-400 mt-2 text-sm">
                Enter your details to get a ticket
              </p>
            </div>

            {message && (
              <div className="mb-6 text-center text-sm text-red-400">
                {message}
              </div>
            )}

            {/* INPUTS */}
            <input
              placeholder="Your Name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-5 py-4 mb-4 rounded-xl bg-white/10 border border-white/10 text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
            />

            <input
              placeholder="Phone (optional)"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full px-5 py-4 mb-6 rounded-xl bg-white/10 border border-white/10 text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
            />

            {/* BUTTON */}
            <button
              onClick={handleJoin}
              disabled={loading || !sessionToken}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold shadow-lg hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50"
            >
              {loading ? "Joining..." : "Confirm & Join Queue"}
            </button>
          </>
        ) : (
          <div className="animate-in fade-in zoom-in duration-300 text-center">
             <div className="w-16 h-16 bg-violet-600/20 text-violet-400 rounded-full flex items-center justify-center mx-auto mb-6 border border-violet-500/30">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                </svg>
             </div>
             <h2 className="text-2xl font-bold text-white mb-2">Guest Registration</h2>
             <p className="text-slate-400 text-sm mb-8">A small registration fee is required to join this session.</p>
             
             <div className="space-y-4">
                <button 
                  onClick={executeJoin}
                  disabled={loading}
                  className="w-full py-4 rounded-2xl bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white font-bold shadow-xl hover:scale-[1.02] transition-transform disabled:opacity-50"
                >
                  {loading ? "Processing..." : "Pay $1.00 & Join"}
                </button>
                <button 
                  onClick={executeJoin}
                  disabled={loading}
                  className="w-full py-4 text-sm font-semibold text-slate-400 hover:text-white transition-colors"
                >
                  Skip Payment (Test Mode)
                </button>
                <button 
                  onClick={() => setShowPayment(false)}
                  disabled={loading}
                  className="w-full text-xs text-red-400/60 font-bold hover:text-red-400 uppercase tracking-widest"
                >
                  Go Back
                </button>
             </div>
          </div>
        )}

        <p className="mt-6 text-center text-xs text-slate-400">
          You will receive a ticket number after joining
        </p>
      </div>
    </div>
  );
}
