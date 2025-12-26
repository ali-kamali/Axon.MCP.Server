import { useEffect, useState } from "react";
import { getOverviewStatistics, OverviewStatistics } from "../../services/api";
import styles from "./OverviewStats.module.css";

export const OverviewStats = () => {
    const [stats, setStats] = useState<OverviewStatistics | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const data = await getOverviewStatistics();
                setStats(data);
            } catch (err) {
                console.error("Failed to fetch overview stats:", err);
                setError("Failed to load statistics");
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
    }, []);

    if (loading) return <div className={styles.loading}>Loading statistics...</div>;
    if (error) return <div className={styles.error}>{error}</div>;
    if (!stats) return null;

    return (
        <div className={styles.container}>
            <h2 className={styles.title}>System Overview</h2>
            <div className={styles.grid}>
                <StatCard label="Repositories" value={stats.total_repositories} />
                <StatCard label="Files" value={stats.total_files} />
                <StatCard label="Symbols" value={stats.total_symbols} />
                <StatCard label="Endpoints" value={stats.total_endpoints} />
                <StatCard label="API Calls" value={stats.total_outgoing_calls} />
                <StatCard label="Events" value={stats.total_published_events} />
            </div>

            <div className={styles.languages}>
                <h3>Top Languages</h3>
                <div className={styles.langGrid}>
                    {stats.top_languages.map((lang) => (
                        <div key={lang.language} className={styles.langItem}>
                            <span className={styles.langName}>{lang.language}</span>
                            <span className={styles.langCount}>{lang.file_count} files</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

const StatCard = ({ label, value }: { label: string; value: number }) => (
    <div className={styles.card}>
        <div className={styles.value}>{value.toLocaleString()}</div>
        <div className={styles.label}>{label}</div>
    </div>
);
