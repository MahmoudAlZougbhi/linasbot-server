import React, { createContext, useContext, useState } from 'react';

const OperatorStatusContext = createContext(null);

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
  return ctx || { operatorStatus: 'available', setOperatorStatus: () => {} };
};
