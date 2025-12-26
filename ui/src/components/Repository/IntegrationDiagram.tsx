import React from 'react';
import { IntegrationSummary } from '../../services/api';
import styles from './IntegrationDiagram.module.css';

interface IntegrationDiagramProps {
    data: IntegrationSummary;
    loading: boolean;
}

export const IntegrationDiagram: React.FC<IntegrationDiagramProps> = ({ data, loading }) => {
    if (loading) return <div className={styles.loading}>Loading integrations...</div>;

    if (!data) return null;

    return (
        <div className={styles.container}>
            <div className={styles.statsGrid}>
                <StatBox label="Outgoing Calls" value={data.summary.outgoing_calls_count} />
                <StatBox label="Published Events" value={data.summary.published_events_count} />
                <StatBox label="Event Types" value={data.top_event_topics.length > 0 ? data.top_event_topics.length : 0} />
                <StatBox label="Endpoint Links" value={data.summary.endpoint_links_count} />
            </div>

            <div className={styles.detailsRow}>
                <div className={styles.detailsColumn}>
                    <h4 className={styles.columnTitle}>Top Outgoing Targets</h4>
                    {data.top_outgoing_targets.length > 0 ? (
                        <ul className={styles.list}>
                            {data.top_outgoing_targets.map((item, idx) => (
                                <li key={idx} className={styles.listItem}>
                                    <span className={styles.targetName}>{item.target}</span>
                                    <span className={styles.countBadge}>{item.count}</span>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className={styles.emptyText}>No outgoing calls detected</p>
                    )}
                </div>

                <div className={styles.detailsColumn}>
                    <h4 className={styles.columnTitle}>Top Event Topics</h4>
                    {data.top_event_topics.length > 0 ? (
                        <ul className={styles.list}>
                            {data.top_event_topics.map((topic, idx) => (
                                <li key={idx} className={styles.listItem}>
                                    <span className={styles.targetName}>{topic}</span>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className={styles.emptyText}>No events published</p>
                    )}
                </div>
            </div>
        </div>
    );
};

const StatBox = ({ label, value }: { label: string; value: number }) => (
    <div className={styles.statBox}>
        <div className={styles.statValue}>{value}</div>
        <div className={styles.statLabel}>{label}</div>
    </div>
);
