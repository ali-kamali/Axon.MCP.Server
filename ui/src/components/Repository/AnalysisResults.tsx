import React, { useEffect, useState } from 'react';
import {
    getRepositoryServices,
    getRepositoryEfEntities,
    getRepositoryIntegrations,
    getRepositoryConfigFindings,
    getRepositoryQualityMetrics,
    ServiceAnalysis,
    EfEntityAnalysis,
    IntegrationSummary,
    ConfigFinding,
    QualityAnalysis
} from '../../services/api';
import { ServicesTable } from './ServicesTable';
import { EfEntitiesTable } from './EfEntitiesTable';
import { IntegrationDiagram } from './IntegrationDiagram';
import styles from './AnalysisResults.module.css';

interface AnalysisResultsProps {
    repositoryId: number;
}

type TabType = 'services' | 'database' | 'integration' | 'config' | 'quality';

export const AnalysisResults: React.FC<AnalysisResultsProps> = ({ repositoryId }) => {
    const [activeTab, setActiveTab] = useState<TabType>('services');

    // Data states
    const [services, setServices] = useState<ServiceAnalysis[]>([]);
    const [entities, setEntities] = useState<EfEntityAnalysis[]>([]);
    const [integrations, setIntegrations] = useState<IntegrationSummary | null>(null);
    const [configFindings, setConfigFindings] = useState<ConfigFinding[]>([]);
    const [qualityMetrics, setQualityMetrics] = useState<QualityAnalysis | null>(null);

    // Loading states
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchAnalysisData = async () => {
            setLoading(true);
            setError(null);
            try {
                // Fetch basic data based on active tab to optimize
                // For MVP, we can fetch all or just fetch on demand
                // Since data size is expected to be small-medium, we'll fetch context relevant to tab

                switch (activeTab) {
                    case 'services':
                        if (services.length === 0) setServices(await getRepositoryServices(repositoryId));
                        break;
                    case 'database':
                        if (entities.length === 0) setEntities(await getRepositoryEfEntities(repositoryId));
                        break;
                    case 'integration':
                        if (!integrations) setIntegrations(await getRepositoryIntegrations(repositoryId));
                        break;
                    case 'config':
                        if (configFindings.length === 0) setConfigFindings(await getRepositoryConfigFindings(repositoryId));
                        break;
                    case 'quality':
                        if (!qualityMetrics) setQualityMetrics(await getRepositoryQualityMetrics(repositoryId));
                        break;
                }
            } catch (err) {
                console.error("Failed to fetch analysis data:", err);
                setError("Failed to load analysis data.");
            } finally {
                setLoading(false);
            }
        };

        if (repositoryId) {
            fetchAnalysisData();
        }
    }, [repositoryId, activeTab]);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}>Analysis Findings</h2>
                <div className={styles.tabs}>
                    <button
                        className={`${styles.tab} ${activeTab === 'services' ? styles.activeTab : ''}`}
                        onClick={() => setActiveTab('services')}
                    >
                        Services
                    </button>
                    <button
                        className={`${styles.tab} ${activeTab === 'database' ? styles.activeTab : ''}`}
                        onClick={() => setActiveTab('database')}
                    >
                        Database
                    </button>
                    <button
                        className={`${styles.tab} ${activeTab === 'integration' ? styles.activeTab : ''}`}
                        onClick={() => setActiveTab('integration')}
                    >
                        Integrations
                    </button>
                    <button
                        className={`${styles.tab} ${activeTab === 'config' ? styles.activeTab : ''}`}
                        onClick={() => setActiveTab('config')}
                    >
                        Configuration
                    </button>
                    <button
                        className={`${styles.tab} ${activeTab === 'quality' ? styles.activeTab : ''}`}
                        onClick={() => setActiveTab('quality')}
                    >
                        Quality
                    </button>
                </div>
            </div>

            <div className={styles.content}>
                {error && <div className={styles.error}>{error}</div>}

                {activeTab === 'services' && (
                    <ServicesTable services={services} loading={loading} />
                )}

                {activeTab === 'database' && (
                    <EfEntitiesTable entities={entities} loading={loading} />
                )}

                {activeTab === 'integration' && integrations && (
                    <IntegrationDiagram data={integrations} loading={loading} />
                )}

                {activeTab === 'integration' && !integrations && loading && (
                    <div className={styles.loading}>Loading integrations...</div>
                )}

                {activeTab === 'config' && (
                    <ConfigFindingsTable findings={configFindings} loading={loading} />
                )}

                {activeTab === 'quality' && (
                    <QualityMetricsPanel metrics={qualityMetrics} loading={loading} />
                )}
            </div>
        </div>
    );
};

// Simple internal components for Config and Quality to avoid too many files
// If they grow, move to separate files

const ConfigFindingsTable = ({ findings, loading }: { findings: ConfigFinding[]; loading: boolean }) => {
    if (loading) return <div className={styles.loading}>Loading configuration findings...</div>;
    if (findings.length === 0) return <div className={styles.empty}>No configuration findings.</div>;

    return (
        <div className={styles.tableContainer}>
            <table className={styles.table}>
                <thead>
                    <tr>
                        <th>Key</th>
                        <th>Value</th>
                        <th>Env</th>
                        <th>Location</th>
                    </tr>
                </thead>
                <tbody>
                    {findings.map((f) => (
                        <tr key={f.id}>
                            <td className={styles.codeFont} title={f.config_key}>
                                {f.config_key.length > 50 ? `${f.config_key.substring(0, 50)}...` : f.config_key}
                                {f.is_secret && <span className={styles.secretBadge}>SECRET</span>}
                            </td>
                            <td className={styles.codeFont}>{f.config_value}</td>
                            <td>{f.environment || 'default'}</td>
                            <td className={styles.metaCell}>
                                <div>{f.file_path}</div>
                                {f.line_number && <div className={styles.lineNumber}>Line {f.line_number}</div>}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

const QualityMetricsPanel = ({ metrics, loading }: { metrics: QualityAnalysis | null; loading: boolean }) => {
    if (loading) return <div className={styles.loading}>Loading quality metrics...</div>;
    if (!metrics) return null;

    return (
        <div>
            <div className={styles.metricsGrid}>
                {metrics.metrics.map((m, idx) => (
                    <div key={idx} className={`${styles.metricCard} ${styles[m.status]}`}>
                        <div className={styles.metricTitle}>{m.category}</div>
                        <div className={styles.metricName}>{m.metric_name}</div>
                        <div className={styles.metricValue}>
                            {m.value} <span className={styles.unit}>{m.unit}</span>
                        </div>
                    </div>
                ))}
            </div>

            <div className={styles.warningList}>
                {metrics.files_with_no_symbols > 0 && (
                    <div className={styles.warningItem}>
                        <span className={styles.warningIcon}>⚠️</span>
                        <span>{metrics.files_with_no_symbols} files have zero extracted symbols (potential parsing issue)</span>
                    </div>
                )}
            </div>
        </div>
    );
};
