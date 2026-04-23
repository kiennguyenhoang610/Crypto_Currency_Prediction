var ctx = document.getElementById('lineChart_predict').getContext('2d');

// Dọn dẹp chuỗi nhãn trục X từ Python
var labels_2_raw = document.getElementById('labels_2').value;
var labels_2Array = labels_2_raw.replace(/[\[\]']/g, '').split(', ');

// Lấy dữ liệu của cả 2 mô hình
var data_2 = JSON.parse(document.getElementById('data_2').value);
var data_rf = JSON.parse(document.getElementById('data_rf').value);

var myChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: labels_2Array,
        datasets: [
            {
                label: 'Decision Tree ($)',
                data: data_2,
                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                borderColor: 'rgb(231, 76, 60)', // Đường màu Đỏ
                borderWidth: 2,
                tension: 0.1
            },
            {
                label: 'Random Forest ($)',
                data: data_rf,
                backgroundColor: 'rgba(41, 155, 99, 0.1)',
                borderColor: 'rgb(41, 155, 99)', // Đường màu Xanh lá
                borderWidth: 2,
                tension: 0.1
            }
        ]
    },
    options: {
        responsive: true
    }
});