/**
 * Main JavaScript
 */

// API base URL
const API_BASE_URL = '';

// Get auth token from localStorage
function getAuthToken() {
    return localStorage.getItem('access_token');
}

// Set auth token in localStorage
function setAuthToken(token) {
    localStorage.setItem('access_token', token);
}

// Remove auth token
function removeAuthToken() {
    localStorage.removeItem('access_token');
    // Also remove from cookie if exists
    document.cookie = 'access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
}

// API fetch with auth
async function apiFetch(url, options = {}) {
    const token = getAuthToken();
    
    const headers = {
        ...options.headers,
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
    }
    
    const response = await fetch(API_BASE_URL + url, {
        ...options,
        headers
    });
    
    // Handle 401 Unauthorized - Session expired
    if (response.status === 401) {
        removeAuthToken();
        // Show session expired message
        alert('세션이 만료되었습니다. 다시 로그인해주세요.');
        window.location.href = '/';
        return;
    }

    // Handle 403 Forbidden - Permission denied
    if (response.status === 403) {
        alert('접근 권한이 없습니다.');
        return response;
    }
    
    return response;
}

// Show error message
function showError(message, elementId = 'error-message') {
    const errorDiv = document.getElementById(elementId);
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        
        // Auto hide after 5 seconds
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    } else {
        alert(message);
    }
}

// Show success message
function showSuccess(message, elementId = 'success-message') {
    const successDiv = document.getElementById(elementId);
    if (successDiv) {
        successDiv.textContent = message;
        successDiv.style.display = 'block';
        
        // Auto hide after 5 seconds
        setTimeout(() => {
            successDiv.style.display = 'none';
        }, 5000);
    } else {
        alert(message);
    }
}

// Format date
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    
    const date = new Date(dateString);
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Format grade badge
function getGradeBadgeClass(grade) {
    if (!grade) return '';
    
    const gradeMap = {
        'S': 'badge-s',
        'A': 'badge-a',
        'B': 'badge-b',
        'C': 'badge-c',
        'D': 'badge-d'
    };
    
    return gradeMap[grade.toUpperCase()] || '';
}

// Confirm dialog
function confirmAction(message) {
    return confirm(message);
}

// Show loading spinner
function showLoading(elementId = 'loading') {
    const loadingDiv = document.getElementById(elementId);
    if (loadingDiv) {
        loadingDiv.style.display = 'block';
    }
}

// Hide loading spinner
function hideLoading(elementId = 'loading') {
    const loadingDiv = document.getElementById(elementId);
    if (loadingDiv) {
        loadingDiv.style.display = 'none';
    }
}

// Export to CSV
async function exportToCSV(departmentId = null) {
    try {
        showLoading();
        
        let url = '/applications/export/csv';
        if (departmentId) {
            url += `?department_id=${departmentId}`;
        }
        
        const response = await apiFetch(url);
        
        if (response.ok) {
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = `applications_${new Date().toISOString().slice(0,10)}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(downloadUrl);
            
            showSuccess('CSV 파일이 다운로드되었습니다.');
        } else {
            showError('CSV 내보내기에 실패했습니다.');
        }
    } catch (error) {
        showError('CSV 내보내기 중 오류가 발생했습니다.');
        console.error(error);
    } finally {
        hideLoading();
    }
}

// Logout
async function logout() {
    if (!confirmAction('로그아웃 하시겠습니까?')) {
        return;
    }
    
    try {
        await apiFetch('/auth/logout', { method: 'POST' });
    } catch (error) {
        console.error('Logout error:', error);
    } finally {
        removeAuthToken();
        window.location.href = '/';
    }
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Check if user is logged in for protected pages
    const isLoginPage = window.location.pathname === '/' || window.location.pathname === '/auth/login';
    const token = getAuthToken();
    
    if (!isLoginPage && !token) {
        window.location.href = '/';
    }
    
    // Add logout handler
    const logoutLinks = document.querySelectorAll('a[href="/auth/logout"]');
    logoutLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    });
});
