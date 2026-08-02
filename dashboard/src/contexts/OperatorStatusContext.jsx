import { createContext, useContext, useState } from "react";

/** @type {import('react').Context<OperatorStatusContextValue | null>} */
const OperatorStatusContext = createContext(/** @type {OperatorStatusContextValue | null} */ (null));

/** @param {{ children: import('react').ReactNode }} props */
export const OperatorStatusProvider = ({ children }) => {
  const [operatorStatus, setOperatorStatus] = useState('available');
  return (
    <OperatorStatusContext.Provider value={{ operatorStatus, setOperatorStatus }}>
      {children}
    </OperatorStatusContext.Provider>
  );
};

export const useOperatorStatus = () => {
  const ctx = useContext(OperatorStatusContext);
  /** @type {OperatorStatusContextValue} */
  const fallback = {
    operatorStatus: 'available',
    setOperatorStatus: () => {},
  };
  return ctx || fallback;
};
