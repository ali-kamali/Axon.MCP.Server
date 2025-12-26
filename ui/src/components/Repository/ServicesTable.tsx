import React, { useState } from 'react';
import { ServiceAnalysis } from '../../services/api';
import styles from './ServicesTable.module.css';

interface ServicesTableProps {
    services: ServiceAnalysis[];
    loading: boolean;
}

export const ServicesTable: React.FC<ServicesTableProps> = ({ services, loading }) => {
    if (loading) {
        return <div className={styles.loading}>Loading services...</div>;
    }

    if (services.length === 0) {
        return <div className={styles.empty}>No services detected in this repository.</div>;
    }

    return (
        <div className={styles.container}>
            <table className={styles.table}>
                <thead>
                    <tr>
                        <th>Service Name</th>
                        <th>Type</th>
                        <th>Framework</th>
                        <th>Entry Points</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    {services.map((service) => (
                        <tr key={service.id}>
                            <td className={styles.nameCell}>
                                <div className={styles.name}>{service.name}</div>
                                {service.description && <div className={styles.description}>{service.description}</div>}
                            </td>
                            <td>
                                <span className={`${styles.badge} ${styles[service.service_type.toLowerCase()] || styles.defaultBadge}`}>
                                    {service.service_type}
                                </span>
                            </td>
                            <td>{service.framework_version || '-'}</td>
                            <td>{service.entry_points_count}</td>
                            <td>{new Date(service.created_at).toLocaleDateString()}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};
