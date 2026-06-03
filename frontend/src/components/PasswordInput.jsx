import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

/**
 * Password input with a built-in show/hide eye toggle.
 * Drop-in replacement for <input type="password" />: forwards all props
 * (value, onChange, placeholder, autoComplete, required, etc.).
 */
export default function PasswordInput({ className = 'input', ...props }) {
    const [show, setShow] = useState(false);
    return (
        <div className="relative">
            <input
                {...props}
                type={show ? 'text' : 'password'}
                className={`${className} pr-10`}
            />
            <button
                type="button"
                onClick={() => setShow((s) => !s)}
                aria-label={show ? 'Hide password' : 'Show password'}
                tabIndex={-1}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-ink-100 dark:hover:text-ink-200 dark:hover:bg-ink-800 transition-colors"
            >
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
        </div>
    );
}
