import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../../services/api";
import styles from "./LoginPage.module.css";

export default function LoginPage() {
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            await login(password);
            navigate("/");
        } catch (err: any) {
            setError("Login failed. Check your password.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={styles.container}>
            <form onSubmit={handleSubmit} className={styles.form}>
                <h2>Axon Server Login</h2>
                {error && <div className={styles.error}>{error}</div>}
                <div className={styles.inputGroup}>
                    <label htmlFor="password">Password</label>
                    <input
                        type="password"
                        id="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        disabled={loading}
                        placeholder="Enter admin password"
                        autoFocus
                    />
                </div>
                <button type="submit" disabled={loading} className={styles.submitButton}>
                    {loading ? "Logging in..." : "Login"}
                </button>
            </form>
        </div>
    );
}
