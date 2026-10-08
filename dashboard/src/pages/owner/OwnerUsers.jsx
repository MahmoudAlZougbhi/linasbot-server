// @ts-nocheck
import { Navigate } from 'react-router-dom';

/** People now live on the business drawer. The old URL still loads. */
export default function OwnerUsers() {
  return <Navigate to="/owner/tenants" replace />;
}
