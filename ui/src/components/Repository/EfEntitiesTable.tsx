import React, { useState } from 'react';
import { EfEntityAnalysis } from '../../services/api';
import styles from './EfEntitiesTable.module.css';

interface EfEntitiesTableProps {
    entities: EfEntityAnalysis[];
    loading: boolean;
}

export const EfEntitiesTable: React.FC<EfEntitiesTableProps> = ({ entities, loading }) => {
    if (loading) {
        return <div className={styles.loading}>Loading entities...</div>;
    }

    if (entities.length === 0) {
        return <div className={styles.empty}>No EF Core entities detected.</div>;
    }

    return (
        <div className={styles.container}>
            <table className={styles.table}>
                <thead>
                    <tr>
                        <th>Entity Name</th>
                        <th>Table</th>
                        <th>Schema</th>
                        <th>Properties</th>
                        <th>Relationships</th>
                    </tr>
                </thead>
                <tbody>
                    {entities.map((entity) => (
                        <tr key={entity.id}>
                            <td className={styles.nameCell}>
                                <div className={styles.name}>{entity.entity_name}</div>
                                {entity.namespace && <div className={styles.namespace}>{entity.namespace}</div>}
                                {entity.has_primary_key && <span className={styles.pkBadge}>PK</span>}
                            </td>
                            <td className={styles.codeFont}>{entity.table_name || '-'}</td>
                            <td className={styles.codeFont}>{entity.schema_name || '-'}</td>
                            <td>{entity.properties_count}</td>
                            <td>{entity.relationships_count}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};
