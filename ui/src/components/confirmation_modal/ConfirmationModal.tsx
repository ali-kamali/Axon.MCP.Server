import { ReactNode } from "react";
import styles from "./ConfirmationModal.module.css";

type ConfirmationModalProps = {
  isOpen: boolean;
  title: string;
  message: string | ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: "danger" | "warning" | "info";
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
};

export default function ConfirmationModal({
  isOpen,
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "warning",
  onConfirm,
  onCancel,
  isLoading = false,
}: ConfirmationModalProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className={styles.modal_overlay}>
      <button
        type="button"
        className={styles.modal_backdrop}
        onClick={onCancel}
        aria-label="Close confirmation modal"
      />
      <div className={styles.modal_container} role="dialog" aria-modal="true" aria-labelledby="confirmation-modal-title">
        <div className={styles.modal_header}>
          <h2 id="confirmation-modal-title" className={styles.modal_title}>
            {title}
          </h2>
        </div>
        <div className={styles.modal_body}>
          {typeof message === "string" ? <p className={styles.modal_message}>{message}</p> : message}
        </div>
        <div className={styles.modal_footer}>
          <button
            type="button"
            className={styles.cancel_button}
            onClick={onCancel}
            disabled={isLoading}
          >
            {cancelText}
          </button>
          <button
            type="button"
            className={`${styles.confirm_button} ${styles[`confirm_${variant}`]}`}
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? "Processing..." : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

