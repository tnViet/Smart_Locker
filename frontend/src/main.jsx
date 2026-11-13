import React from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserRouter,Navigate,Route,Routes,useLocation} from 'react-router-dom';
import {AuthProvider,useAuth} from './context/AuthContext';
import {ToastProvider} from './context/ToastContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Compartments from './pages/Compartments';
import Sessions from './pages/Sessions';
import Users from './pages/Users';
import Statistics from './pages/Statistics';
import Devices from './pages/Devices';
import FeeRules from './pages/FeeRules';
import './styles/main.css';
function Protected({children}){const {auth}=useAuth();const loc=useLocation();return auth?children:<Navigate to="/login" replace state={{from:loc.pathname}}/>}
function Shell(){const {auth}=useAuth();return <Routes>
 <Route path="/login" element={auth?<Navigate to="/" replace/>:<Login/>}/>
 <Route element={<Protected><Layout/></Protected>}>
  <Route index element={<Dashboard/>}/><Route path="/compartments" element={<Compartments/>}/><Route path="/sessions" element={<Sessions/>}/><Route path="/users" element={<Users/>}/><Route path="/statistics" element={<Statistics/>}/><Route path="/devices" element={<Devices/>}/><Route path="/fee-rules" element={<FeeRules/>}/>
 </Route>
 <Route path="*" element={<Navigate to="/" replace/>}/>
 </Routes>}
createRoot(document.getElementById('root')).render(<React.StrictMode><BrowserRouter><AuthProvider><ToastProvider><Shell/></ToastProvider></AuthProvider></BrowserRouter></React.StrictMode>);
