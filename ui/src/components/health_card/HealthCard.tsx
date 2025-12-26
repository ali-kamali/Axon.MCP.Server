import styles from "./HealthCard.module.css";

export type HealthCardProps = {
  status: string;
  service: string;
  version: string;
  environment: string;
};

export default function HealthCard(props: HealthCardProps) {
  const { status, service, version, environment } = props;
  return (
    <section className={styles.health_container}>
      <div className={styles.health_header}>{service}</div>
      <div className={styles.health_grid}>
        <div className={styles.health_item}>
          <span className={styles.health_label}>Status</span>
          <span className={styles.health_value}>{status}</span>
        </div>
        <div className={styles.health_item}>
          <span className={styles.health_label}>Environment</span>
          <span className={styles.health_value}>{environment}</span>
        </div>
        <div className={styles.health_item}>
          <span className={styles.health_label}>Version</span>
          <span className={styles.health_value}>{version}</span>
        </div>
      </div>
    </section>
  );
}


