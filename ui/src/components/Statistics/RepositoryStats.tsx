import { useEffect, useState } from "react";
import { getRepositoryStatistics, RepositoryStatistics } from "../../services/api";
import styles from "./RepositoryStats.module.css";

interface Props {
    repositoryId: number;
}

export const RepositoryStats = ({ repositoryId }: Props) => {
    const [stats, setStats] = useState<RepositoryStatistics | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                setLoading(true);
                const data = await getRepositoryStatistics(repositoryId);
                setStats(data);
            } catch (err) {
                console.error("Failed to fetch repository stats:", err);
                setError("Failed to load statistics");
            } finally {
                setLoading(false);
            }
        };

        if (repositoryId) {
            fetchStats();
        }
    }, [repositoryId]);

    if (loading) return <div className={styles.loading}>Loading statistics...</div>;
    if (error) return <div className={styles.error}>{error}</div>;
    if (!stats) return null;

    return (
        <div className={styles.container}>
            <div className={styles.section}>
                <h3 className={styles.sectionTitle}>Key Metrics</h3>
                <div className={styles.grid}>
                    <StatCard label="Files" value={stats.total_files} />
                    <StatCard label="Symbols" value={stats.total_symbols} />
                    <StatCard label="Endpoints" value={stats.total_endpoints} />
                    <StatCard label="Module Summaries" value={stats.total_module_summaries} />
                    <StatCard label="Avg Symbols/File" value={stats.avg_symbols_per_file} />
                </div>

                {stats.files_with_no_symbols > 0 && (
                    <div className={styles.alert}>
                        ⚠️ {stats.files_with_no_symbols} files have no extracted symbols. This might indicate parsing issues.
                    </div>
                )}
            </div>

            <div className={styles.row}>
                <div className={styles.column}>
                    <h3 className={styles.sectionTitle}>Symbol Distribution</h3>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>Type</th>
                                <th>Count</th>
                            </tr>
                        </thead>
                        <tbody>
                            {stats.symbol_distribution.map((item) => (
                                <tr key={item.kind}>
                                    <td>{item.kind}</td>
                                    <td>{item.count.toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className={styles.column}>
                    <h3 className={styles.sectionTitle}>Relationships</h3>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>Type</th>
                                <th>Count</th>
                            </tr>
                        </thead>
                        <tbody>
                            {stats.relationship_distribution.map((item) => (
                                <tr key={item.relation_type}>
                                    <td>{item.relation_type}</td>
                                    <td>{item.count.toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            <div className={styles.section}>
                <h3 className={styles.sectionTitle}>Integration</h3>
                <div className={styles.grid}>
                    <StatCard label="Outgoing API Calls" value={stats.total_outgoing_calls} />
                    <StatCard label="Published Events" value={stats.total_published_events} />
                    <StatCard label="Event Subscriptions" value={stats.total_event_subscriptions} />
                </div>
            </div>
        </div>
    );
};

const StatCard = ({ label, value }: { label: string; value: number | string }) => (
    <div className={styles.card}>
        <div className={styles.value}>{typeof value === 'number' ? value.toLocaleString() : value}</div>
        <div className={styles.label}>{label}</div>
    </div>
);
