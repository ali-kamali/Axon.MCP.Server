import { useEffect } from "react";
import styles from "./Toast.module.css";

export enum ToastTypeEnum {
  success = "success",
  error = "error",
  warning = "warning",
  info = "info",
}

type ToastProps = {
  message: string;
  type?: ToastTypeEnum;
  duration?: number;
  onClose: () => void;
};

export default function Toast({ message, type = ToastTypeEnum.info, duration = 5000, onClose }: ToastProps) {
  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onClose();
      }, duration);

      return () => clearTimeout(timer);
    }
  }, [duration, onClose]);

  return (
    <div className={`${styles.toast_container} ${styles[`toast_${type}`]}`}>
      <div className={styles.toast_content}>
        <span className={styles.toast_icon}>{getIcon(type)}</span>
        <span className={styles.toast_message}>{message}</span>
      </div>
      <button type="button" className={styles.toast_close} onClick={onClose} aria-label="Close notification">
        ×
      </button>
    </div>
  );
}

function getIcon(type: ToastTypeEnum): string {
  switch (type) {
    case ToastTypeEnum.success:
      return "✓";
    case ToastTypeEnum.error:
      return "✕";
    case ToastTypeEnum.warning:
      return "⚠";
    case ToastTypeEnum.info:
    default:
      return "ℹ";
  }
}

