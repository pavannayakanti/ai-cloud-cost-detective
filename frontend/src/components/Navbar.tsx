import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <nav className="border-b border-slate-800 bg-slate-900/60 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
        <Link to="/dashboard" className="text-lg font-semibold text-white">
          AI Cloud Cost Detective
        </Link>
        <div className="flex items-center gap-6 text-sm">
          <Link to="/dashboard" className="text-slate-300 hover:text-white">
            Dashboard
          </Link>
          <Link to="/history" className="text-slate-300 hover:text-white">
            History
          </Link>
          <span className="hidden text-slate-500 sm:inline">{user?.email}</span>
          <button
            onClick={handleLogout}
            className="rounded-md bg-slate-800 px-3 py-1.5 text-slate-200 hover:bg-slate-700"
          >
            Log out
          </button>
        </div>
      </div>
    </nav>
  );
}
