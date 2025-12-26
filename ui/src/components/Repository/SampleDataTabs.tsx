import React, { useState, useEffect } from 'react';
import { getRepositorySamples, RepositorySamples } from '../../services/api';
import styles from './SampleDataTabs.module.css';

interface SampleDataTabsProps {
    repositoryId: number;
}

type TabType = 'outgoing_calls' | 'published_events' | 'event_subscriptions' | 'endpoints' | 'module_summaries';

const SampleDataTabs: React.FC<SampleDataTabsProps> = ({ repositoryId }) => {
    const [activeTab, setActiveTab] = useState<TabType>('outgoing_calls');
    const [samples, setSamples] = useState<RepositorySamples | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchSamples = async () => {
            try {
                setLoading(true);
                const data = await getRepositorySamples(repositoryId);
                setSamples(data);
                setError(null);
            } catch (err) {
                setError('Failed to load sample data');
                console.error('Error fetching samples:', err);
            } finally {
                setLoading(false);
            }
        };

        fetchSamples();
    }, [repositoryId]);

    if (loading) {
        return <div className={styles.loading}>Loading samples...</div>;
    }

    if (error) {
        return <div className={styles.error}>{error}</div>;
    }

    if (!samples) {
        return null;
    }

    const tabs = [
        { key: 'outgoing_calls' as TabType, label: 'Outgoing API Calls', count: samples.outgoing_calls.length },
        { key: 'published_events' as TabType, label: 'Published Events', count: samples.published_events.length },
        { key: 'event_subscriptions' as TabType, label: 'Event Subscriptions', count: samples.event_subscriptions.length },
        { key: 'endpoints' as TabType, label: 'Endpoints', count: samples.endpoints.length },
        { key: 'module_summaries' as TabType, label: 'Module Summaries', count: samples.module_summaries.length },
    ];

    return (
        <div className={styles.container}>
            <h2 className={styles.title}>Sample Data</h2>

            <div className={styles.tabs}>
                {tabs.map(tab => (
                    <button
                        key={tab.key}
                        className={`${styles.tab} ${activeTab === tab.key ? styles.activeTab : ''}`}
                        onClick={() => setActiveTab(tab.key)}
                    >
                        {tab.label} ({tab.count})
                    </button>
                ))}
            </div>

            <div className={styles.tabContent}>
                {activeTab === 'outgoing_calls' && (
                    <div className={styles.tableWrapper}>
                        {samples.outgoing_calls.length === 0 ? (
                            <p className={styles.emptyMessage}>No outgoing API calls found</p>
                        ) : (
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Method</th>
                                        <th>URL Pattern</th>
                                        <th>Client Library</th>
                                        <th>File</th>
                                        <th>Line</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {samples.outgoing_calls.map(call => (
                                        <tr key={call.id}>
                                            <td><span className={styles.badge}>{call.http_method}</span></td>
                                            <td className={styles.codeText}>{call.url_pattern}</td>
                                            <td>{call.http_client_library || '-'}</td>
                                            <td className={styles.filePath}>{call.file_path || '-'}</td>
                                            <td>{call.line_number || '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                )}

                {activeTab === 'published_events' && (
                    <div className={styles.tableWrapper}>
                        {samples.published_events.length === 0 ? (
                            <p className={styles.emptyMessage}>No published events found</p>
                        ) : (
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Event Type</th>
                                        <th>Messaging Library</th>
                                        <th>File</th>
                                        <th>Line</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {samples.published_events.map(event => (
                                        <tr key={event.id}>
                                            <td className={styles.codeText}>{event.event_type_name}</td>
                                            <td>{event.messaging_library || '-'}</td>
                                            <td className={styles.filePath}>{event.file_path || '-'}</td>
                                            <td>{event.line_number || '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                )}

                {activeTab === 'event_subscriptions' && (
                    <div className={styles.tableWrapper}>
                        {samples.event_subscriptions.length === 0 ? (
                            <p className={styles.emptyMessage}>No event subscriptions found</p>
                        ) : (
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Event Type</th>
                                        <th>Handler Class</th>
                                        <th>Messaging Library</th>
                                        <th>File</th>
                                        <th>Line</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {samples.event_subscriptions.map(sub => (
                                        <tr key={sub.id}>
                                            <td className={styles.codeText}>{sub.event_type_name}</td>
                                            <td className={styles.codeText}>{sub.handler_class_name || '-'}</td>
                                            <td>{sub.messaging_library || '-'}</td>
                                            <td className={styles.filePath}>{sub.file_path || '-'}</td>
                                            <td>{sub.line_number || '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                )}

                {activeTab === 'endpoints' && (
                    <div className={styles.tableWrapper}>
                        {samples.endpoints.length === 0 ? (
                            <p className={styles.emptyMessage}>No endpoints found</p>
                        ) : (
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Endpoint</th>
                                        <th>Signature</th>
                                        <th>File</th>
                                        <th>Line</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {samples.endpoints.map(endpoint => (
                                        <tr key={endpoint.id}>
                                            <td className={styles.codeText}>{endpoint.name}</td>
                                            <td className={styles.codeText}>{endpoint.signature || '-'}</td>
                                            <td className={styles.filePath}>{endpoint.file_path || '-'}</td>
                                            <td>{endpoint.line_number}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                )}

                {activeTab === 'module_summaries' && (
                    <div className={styles.tableWrapper}>
                        {samples.module_summaries.length === 0 ? (
                            <p className={styles.emptyMessage}>No module summaries found</p>
                        ) : (
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Module Name</th>
                                        <th>Path</th>
                                        <th>Summary</th>
                                        <th>Files</th>
                                        <th>Symbols</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {samples.module_summaries.map(module => (
                                        <tr key={module.id}>
                                            <td className={styles.codeText}>{module.module_name}</td>
                                            <td className={styles.filePath}>{module.module_path}</td>
                                            <td className={styles.summary}>{module.summary}</td>
                                            <td>{module.file_count}</td>
                                            <td>{module.symbol_count}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default SampleDataTabs;
